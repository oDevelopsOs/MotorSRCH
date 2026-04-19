package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"html"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/bits-and-blooms/bloom/v3"
	"github.com/gocolly/colly/v2"
	"github.com/google/uuid"
	"github.com/mendableai/firecrawl-go/v2"
	"github.com/mmcdole/gofeed"
	"github.com/nsqio/go-nsq"
	"github.com/redis/go-redis/v9"
)

// Cliente HTTP con timeout largo para Crawl4AI / Firecrawl (Playwright).
var httpLong = &http.Client{Timeout: 120 * time.Second}

type rawPage struct {
	ID             string `json:"id"`
	URL            string `json:"url"`
	Title          string `json:"title"`
	HTML           string `json:"html"`
	Domain         string `json:"domain"`
	FetchedAt      string `json:"fetched_at"`
	Via            string `json:"via"`
	ContentType    string `json:"content_type,omitempty"`
	SeedName       string `json:"seed_name,omitempty"`
	SeedCategory   string `json:"seed_category,omitempty"`
	SeedRegion     string `json:"seed_region,omitempty"`
	SeedLang       string `json:"seed_lang,omitempty"`
	SeedPriority   int    `json:"seed_priority,omitempty"`
	CrawlStrategy  string `json:"crawl_strategy,omitempty"`
}

type fetchConfig struct {
	flareURL         string
	flareDomains     map[string]struct{}
	crawl4aiURL      string
	crawl4All        bool
	crawl4Domains    map[string]struct{}
	firecrawlURL     string
	firecrawlKey     string
	firecrawlSDK     *firecrawl.FirecrawlApp // no nil si FIRECRAWL_URL está definido (SDK obligatorio)
	firecrawlAll     bool
	firecrawlDomains map[string]struct{}
	camoufoxURL      string
	camoufoxAll      bool
	camoufoxDomains  map[string]struct{}
	camoufoxToken    string
	scrappeyBase     string
	scrappeyKey      string
	scrappeyAll      bool
	scrappeyDomains  map[string]struct{}
	curlBin          string
	curlHTTPProxy    string
	torProxy         string
	collyHTTPProxy   string
}

func main() {
	nsqd := getenv("NSQD_ADDR", "nsqd:4150")
	redisURL := getenv("REDIS_URL", "redis://redis:6379/0")
	flareURL := getenv("FLARESOLVERR_URL", "http://flaresolverr:8191")
	crawl4aiURL := strings.TrimSpace(os.Getenv("CRAWL4AI_URL"))
	crawl4All, crawl4Domains := parseDomainSet(os.Getenv("CRAWL4AI_DOMAINS"))
	firecrawlURL := strings.TrimSpace(os.Getenv("FIRECRAWL_URL"))
	firecrawlKey := os.Getenv("FIRECRAWL_API_KEY")
	firecrawlAll, firecrawlDomains := parseDomainSet(os.Getenv("FIRECRAWL_DOMAINS"))
	curlBin := getenv("CURL_IMPERSONATE_PATH", "")
	torProxy := os.Getenv("TOR_PROXY")
	collyHTTPProxy := strings.TrimSpace(os.Getenv("COLLY_HTTP_PROXY"))
	curlHTTPProxy := strings.TrimSpace(os.Getenv("CURL_HTTP_PROXY"))

	camoufoxURL := strings.TrimSpace(os.Getenv("CAMOUFOX_URL"))
	camoufoxAll, camoufoxDomains := parseDomainSet(os.Getenv("CAMOUFOX_DOMAINS"))
	camoufoxToken := strings.TrimSpace(os.Getenv("CAMOUFOX_BRIDGE_TOKEN"))

	scrappeyBase := strings.TrimSpace(os.Getenv("SCRAPPEY_URL"))
	if scrappeyBase == "" {
		scrappeyBase = "https://publisher.scrappey.com"
	}
	scrappeyKey := strings.TrimSpace(os.Getenv("SCRAPPEY_API_KEY"))
	scrappeyAll, scrappeyDomains := parseDomainSet(os.Getenv("SCRAPPEY_DOMAINS"))

	flareDomains := map[string]struct{}{}
	for _, d := range strings.Split(os.Getenv("FLARE_DOMAINS"), ",") {
		d = strings.TrimSpace(strings.ToLower(d))
		if d != "" {
			flareDomains[d] = struct{}{}
		}
	}

	var firecrawlApp *firecrawl.FirecrawlApp
	if firecrawlURL != "" {
		sdkKey := firecrawlKey
		if strings.TrimSpace(sdkKey) == "" {
			sdkKey = "dummy"
		}
		var errInit error
		firecrawlApp, errInit = firecrawl.NewFirecrawlApp(sdkKey, firecrawlURL, 120*time.Second)
		if errInit != nil {
			log.Fatalf("Firecrawl: FIRECRAWL_URL está definido pero el SDK github.com/mendableai/firecrawl-go/v2 no pudo inicializarse: %v", errInit)
		}
	}

	fetchCfg := fetchConfig{
		flareURL:         flareURL,
		flareDomains:     flareDomains,
		crawl4aiURL:      crawl4aiURL,
		crawl4All:        crawl4All,
		crawl4Domains:    crawl4Domains,
		firecrawlURL:     firecrawlURL,
		firecrawlKey:     firecrawlKey,
		firecrawlSDK:     firecrawlApp,
		firecrawlAll:     firecrawlAll,
		firecrawlDomains: firecrawlDomains,
		camoufoxURL:      camoufoxURL,
		camoufoxAll:      camoufoxAll,
		camoufoxDomains:  camoufoxDomains,
		camoufoxToken:    camoufoxToken,
		scrappeyBase:     scrappeyBase,
		scrappeyKey:      scrappeyKey,
		scrappeyAll:      scrappeyAll,
		scrappeyDomains:  scrappeyDomains,
		curlBin:          curlBin,
		curlHTTPProxy:    curlHTTPProxy,
		torProxy:         torProxy,
		collyHTTPProxy:   collyHTTPProxy,
	}

	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		log.Fatalf("redis url: %v", err)
	}
	rdb := redis.NewClient(opt)

	cfg := nsq.NewConfig()
	producer, err := nsq.NewProducer(nsqd, cfg)
	if err != nil {
		log.Fatalf("nsq producer: %v", err)
	}
	defer producer.Stop()

	bloomFilter := loadOrCreateBloom(rdb)

	seedsPath := getenv("SEEDS_PATH", "seeds.json")
	intervalMin, _ := strconv.Atoi(getenv("CRAWL_INTERVAL_MINUTES", "0"))

	for round := 0; ; round++ {
		data, err := os.ReadFile(seedsPath)
		if err != nil {
			log.Fatalf("read seeds: %v", err)
		}
		seeds, err := parseSeeds(data)
		if err != nil {
			log.Fatalf("parse seeds: %v", err)
		}
		if seeds.Version != "" {
			log.Printf("crawler: seeds version %s — %s", seeds.Version, seeds.Description)
		}

		fp := gofeed.NewParser()
		fp.UserAgent = "MotorDeBusqueda/1.0 (research bot; contact: compliance@example.com)"
		ctx := context.Background()

		var wg sync.WaitGroup
		sem := make(chan struct{}, 4)

		for i := range seeds.Feeds {
			sf := &seeds.Feeds[i]
			feedURL := strings.TrimSpace(sf.URL)
			if feedURL == "" {
				continue
			}
			hint := hintFromFeed(sf)
			wg.Add(1)
			sem <- struct{}{}
			go func(feedURL string, hint *seedHint) {
				defer wg.Done()
				defer func() { <-sem }()
				feed, err := fp.ParseURLWithContext(feedURL, ctx)
				if err != nil {
					log.Printf("feed parse %s: %v", feedURL, err)
					return
				}
				for _, it := range feed.Items {
					if it.Link == "" {
						continue
					}
					u := strings.TrimSpace(it.Link)
					if !seenTest(bloomFilter, rdb, ctx, u) {
						continue
					}
					title := it.Title
					fetchAndPublish(ctx, producer, rdb, bloomFilter, &fetchCfg, u, title, hint)
				}
			}(feedURL, hint)
		}
		wg.Wait()

		for i := range seeds.URLs {
			su := &seeds.URLs[i]
			pageURL := resolveEnvInSeedURL(strings.TrimSpace(su.URL))
			if pageURL == "" {
				continue
			}
			if !seenTest(bloomFilter, rdb, ctx, pageURL) {
				continue
			}
			hint := hintFromURL(su)
			fetchAndPublish(ctx, producer, rdb, bloomFilter, &fetchCfg, pageURL, "", hint)
		}

		log.Printf("crawler: seed batch done (round %d)", round)
		if intervalMin <= 0 {
			break
		}
		time.Sleep(time.Duration(intervalMin) * time.Minute)
	}
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

// resolveEnvInSeedURL sustituye placeholders en URLs de seeds (p. ej. FRED con api_key vacío).
func resolveEnvInSeedURL(raw string) string {
	k := strings.TrimSpace(os.Getenv("FRED_API_KEY"))
	if k == "" || !strings.Contains(raw, "api.stlouisfed.org") {
		return raw
	}
	if strings.Contains(raw, "api_key=&") {
		return strings.Replace(raw, "api_key=&", "api_key="+url.QueryEscape(k)+"&", 1)
	}
	return raw
}

func hostKey(raw string) string {
	pu, err := url.Parse(raw)
	if err != nil {
		return "unknown"
	}
	return strings.ToLower(pu.Hostname())
}

func seenTest(bf *bloom.BloomFilter, rdb *redis.Client, ctx context.Context, rawURL string) bool {
	h := sha256.Sum256([]byte(rawURL))
	key := "seen:" + hex.EncodeToString(h[:16])
	if v, _ := rdb.Get(ctx, key).Result(); v == "1" {
		return false
	}
	if bf.Test([]byte(rawURL)) {
		return false
	}
	return true
}

func seenCommit(bf *bloom.BloomFilter, rdb *redis.Client, ctx context.Context, rawURL string) {
	h := sha256.Sum256([]byte(rawURL))
	key := "seen:" + hex.EncodeToString(h[:16])
	bf.Add([]byte(rawURL))
	_ = rdb.Set(ctx, key, "1", 0).Err()
	persistBloom(rdb, bf)
}

func rateAllow(ctx context.Context, rdb *redis.Client, host string) bool {
	if host == "" || host == "unknown" {
		return true
	}
	slot := time.Now().UTC().Truncate(time.Minute).Unix()
	k := "rl:" + host + ":" + strconv.FormatInt(slot, 10)
	n, err := rdb.Incr(ctx, k).Result()
	if err != nil {
		return true
	}
	if n == 1 {
		_ = rdb.Expire(ctx, k, 2*time.Minute).Err()
	}
	return n <= 60
}

func loadOrCreateBloom(rdb *redis.Client) *bloom.BloomFilter {
	const key = "bloom:urls"
	ctx := context.Background()
	data, err := rdb.Get(ctx, key).Bytes()
	if err == nil && len(data) > 0 {
		var bf bloom.BloomFilter
		if err := bf.UnmarshalBinary(data); err == nil {
			return &bf
		}
	}
	bf := bloom.NewWithEstimates(2_000_000, 0.001)
	return bf
}

func persistBloom(rdb *redis.Client, bf *bloom.BloomFilter) {
	ctx := context.Background()
	data, err := bf.MarshalBinary()
	if err != nil {
		return
	}
	_ = rdb.Set(ctx, "bloom:urls", data, 0).Err()
}

// parseDomainSet interpreta una lista "a,b,c" o "*" (todos los hosts).
func parseDomainSet(env string) (all bool, domains map[string]struct{}) {
	domains = map[string]struct{}{}
	for _, d := range strings.Split(env, ",") {
		d = strings.TrimSpace(strings.ToLower(d))
		if d == "" {
			continue
		}
		if d == "*" {
			all = true
			return all, domains
		}
		domains[d] = struct{}{}
	}
	return all, domains
}

func domainPolicyMatch(host string, baseURL string, all bool, domains map[string]struct{}) bool {
	if strings.TrimSpace(baseURL) == "" {
		return false
	}
	if all {
		return true
	}
	if len(domains) == 0 {
		return false
	}
	_, ok := domains[host]
	return ok
}

func wrapMarkdownHTML(md string) string {
	esc := html.EscapeString(md)
	return "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title></title></head><body><article><pre>" + esc + "</pre></article></body></html>"
}

func fetchCrawl4AI(ctx context.Context, base, pageURL string) (string, error) {
	payload := map[string]any{"urls": []string{pageURL}}
	b, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	u := strings.TrimRight(base, "/") + "/crawl"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(b))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := httpLong.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		s := string(raw)
		if len(s) > 500 {
			s = s[:500]
		}
		return "", fmt.Errorf("crawl4ai: HTTP %d: %s", resp.StatusCode, s)
	}
	var out struct {
		Success bool `json:"success"`
		Results []struct {
			Success      bool   `json:"success"`
			HTML         string `json:"html"`
			CleanedHTML  string `json:"cleaned_html"`
			Markdown     string `json:"markdown"`
			ErrorMessage string `json:"error_message"`
		} `json:"results"`
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		return "", err
	}
	if !out.Success || len(out.Results) == 0 {
		return "", fmt.Errorf("crawl4ai: success=false or sin results")
	}
	r0 := out.Results[0]
	if !r0.Success {
		if strings.TrimSpace(r0.ErrorMessage) != "" {
			return "", fmt.Errorf("crawl4ai: %s", r0.ErrorMessage)
		}
		return "", fmt.Errorf("crawl4ai: resultado fallido")
	}
	switch {
	case strings.TrimSpace(r0.CleanedHTML) != "":
		return r0.CleanedHTML, nil
	case strings.TrimSpace(r0.HTML) != "":
		return r0.HTML, nil
	case strings.TrimSpace(r0.Markdown) != "":
		return wrapMarkdownHTML(r0.Markdown), nil
	default:
		return "", fmt.Errorf("crawl4ai: contenido vacío")
	}
}

func fetchFirecrawl(ctx context.Context, cfg *fetchConfig, pageURL string) (string, error) {
	if cfg.firecrawlSDK == nil {
		return "", fmt.Errorf("firecrawl: SDK no inicializado; define FIRECRAWL_URL (y FIRECRAWL_API_KEY si aplica)")
	}
	return fetchFirecrawlSDK(ctx, cfg.firecrawlSDK, pageURL)
}

func fetchFirecrawlSDK(ctx context.Context, app *firecrawl.FirecrawlApp, pageURL string) (string, error) {
	if err := ctx.Err(); err != nil {
		return "", err
	}
	params := &firecrawl.ScrapeParams{
		Formats: []string{"rawHtml", "html", "markdown"},
	}
	doc, err := app.ScrapeURL(pageURL, params)
	if err != nil {
		return "", err
	}
	if doc == nil {
		return "", fmt.Errorf("firecrawl sdk: documento nil")
	}
	switch {
	case strings.TrimSpace(doc.RawHTML) != "":
		return doc.RawHTML, nil
	case strings.TrimSpace(doc.HTML) != "":
		return doc.HTML, nil
	case strings.TrimSpace(doc.Markdown) != "":
		return wrapMarkdownHTML(doc.Markdown), nil
	default:
		return "", fmt.Errorf("firecrawl sdk: contenido vacío")
	}
}

func fetchAndPublish(
	ctx context.Context,
	producer *nsq.Producer,
	rdb *redis.Client,
	bf *bloom.BloomFilter,
	cfg *fetchConfig,
	pageURL, titleHint string,
	hint *seedHint,
) {
	host := hostKey(pageURL)
	if !rateAllow(ctx, rdb, host) {
		log.Printf("rate limited %s", host)
		return
	}

	lowerHost := strings.ToLower(host)

	var html string
	var via string
	var err error
	var title string

	if domainPolicyMatch(lowerHost, cfg.crawl4aiURL, cfg.crawl4All, cfg.crawl4Domains) {
		html, err = fetchCrawl4AI(ctx, cfg.crawl4aiURL, pageURL)
		if err == nil && strings.TrimSpace(html) != "" {
			via, title = "crawl4ai", titleHint
		} else {
			if err != nil {
				log.Printf("crawl4ai %s: %v", pageURL, err)
			}
			html = ""
		}
	}

	if html == "" && domainPolicyMatch(lowerHost, cfg.firecrawlURL, cfg.firecrawlAll, cfg.firecrawlDomains) {
		html, err = fetchFirecrawl(ctx, cfg, pageURL)
		if err == nil && strings.TrimSpace(html) != "" {
			via, title = "firecrawl", titleHint
		} else {
			if err != nil {
				log.Printf("firecrawl %s: %v", pageURL, err)
			}
			html = ""
		}
	}

	if html == "" && domainPolicyMatch(lowerHost, cfg.camoufoxURL, cfg.camoufoxAll, cfg.camoufoxDomains) {
		html, err = fetchCamoufoxBridge(ctx, cfg.camoufoxURL, cfg.camoufoxToken, pageURL)
		if err == nil && strings.TrimSpace(html) != "" {
			via, title = "camoufox", titleHint
		} else {
			if err != nil {
				log.Printf("camoufox %s: %v", pageURL, err)
			}
			html = ""
		}
	}

	if html == "" {
		_, useFlare := cfg.flareDomains[lowerHost]
		switch {
		case useFlare:
			html, err = fetchFlareSolverr(ctx, cfg.flareURL, pageURL)
			via, title = "flare", titleHint
		case cfg.scrappeyKey != "" && domainPolicyMatch(lowerHost, cfg.scrappeyBase, cfg.scrappeyAll, cfg.scrappeyDomains):
			html, err = fetchScrappey(ctx, cfg.scrappeyBase, cfg.scrappeyKey, pageURL)
			if err == nil && strings.TrimSpace(html) != "" {
				via, title = "scrappey", titleHint
			} else {
				if err != nil {
					log.Printf("scrappey %s: %v", pageURL, err)
				}
				html = ""
			}
		case cfg.curlBin != "" && fileExists(cfg.curlBin):
			html, err = fetchCurlImpersonate(ctx, cfg.curlBin, cfg.curlHTTPProxy, pageURL)
			via, title = "curlimp", titleHint
		default:
			html, title, err = fetchColly(cfg, pageURL, titleHint)
			via = "colly"
		}
	}
	if err != nil {
		log.Printf("fetch %s: %v", pageURL, err)
		return
	}
	if len(html) > 900_000 {
		html = html[:900_000]
	}
	if strings.TrimSpace(title) == "" {
		title = titleHint
	}

	id := uuid.NewString()
	u, _ := url.Parse(pageURL)
	domain := ""
	if u != nil {
		domain = u.Hostname()
	}

	msg := rawPage{
		ID:          id,
		URL:         pageURL,
		Title:       title,
		HTML:        html,
		Domain:      domain,
		FetchedAt:   time.Now().UTC().Format(time.RFC3339),
		Via:         via,
		ContentType: "text/html",
	}
	if hint != nil {
		msg.SeedName = hint.Name
		msg.SeedCategory = hint.Category
		msg.SeedRegion = hint.Region
		msg.SeedLang = hint.Lang
		msg.SeedPriority = hint.Priority
		msg.CrawlStrategy = hint.CrawlStrategy
	}
	body, err := json.Marshal(msg)
	if err != nil {
		return
	}
	if err := producer.Publish("raw_pages", body); err != nil {
		log.Printf("nsq publish: %v", err)
		return
	}
	seenCommit(bf, rdb, ctx, pageURL)
}

func fileExists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

func fetchCamoufoxBridge(ctx context.Context, base, authToken, pageURL string) (string, error) {
	payload := map[string]any{
		"url":        pageURL,
		"timeout_ms": 120_000,
	}
	b, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	u := strings.TrimRight(base, "/") + "/v1/fetch"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(b))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	if authToken != "" {
		req.Header.Set("Authorization", "Bearer "+authToken)
	}
	resp, err := httpLong.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		s := string(raw)
		if len(s) > 500 {
			s = s[:500]
		}
		return "", fmt.Errorf("camoufox bridge: HTTP %d: %s", resp.StatusCode, s)
	}
	var out struct {
		OK    bool   `json:"ok"`
		HTML  string `json:"html"`
		Error string `json:"error"`
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		return "", err
	}
	if !out.OK {
		if strings.TrimSpace(out.Error) != "" {
			return "", fmt.Errorf("camoufox bridge: %s", out.Error)
		}
		return "", fmt.Errorf("camoufox bridge: ok=false")
	}
	return out.HTML, nil
}

func fetchScrappey(ctx context.Context, apiBase, apiKey, pageURL string) (string, error) {
	if strings.TrimSpace(apiKey) == "" {
		return "", fmt.Errorf("scrappey: SCRAPPEY_API_KEY vacío")
	}
	payload := map[string]any{
		"cmd":        "request.get",
		"url":        pageURL,
		"maxTimeout": 60000,
	}
	b, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	ep := strings.TrimRight(apiBase, "/") + "/api/v1?key=" + url.QueryEscape(apiKey)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, ep, bytes.NewReader(b))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := httpLong.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		s := string(raw)
		if len(s) > 500 {
			s = s[:500]
		}
		return "", fmt.Errorf("scrappey: HTTP %d: %s", resp.StatusCode, s)
	}
	var out struct {
		Solution struct {
			Verified bool   `json:"verified"`
			Response string `json:"response"`
			Error    string `json:"error"`
		} `json:"solution"`
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		return "", err
	}
	if !out.Solution.Verified {
		msg := strings.TrimSpace(out.Solution.Error)
		if msg == "" {
			msg = "verified=false"
		}
		return "", fmt.Errorf("scrappey: %s", msg)
	}
	return out.Solution.Response, nil
}

func fetchFlareSolverr(ctx context.Context, flareBase, pageURL string) (string, error) {
	payload := map[string]any{
		"cmd":        "request.get",
		"url":        pageURL,
		"maxTimeout": 60000,
	}
	b, _ := json.Marshal(payload)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(flareBase, "/")+"/v1", bytes.NewReader(b))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	var out struct {
		Solution struct {
			Response string `json:"response"`
		} `json:"solution"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", err
	}
	return out.Solution.Response, nil
}

func fetchCurlImpersonate(ctx context.Context, curlBin, httpProxy, pageURL string) (string, error) {
	args := []string{"-sL", "--max-time", "120"}
	if strings.TrimSpace(httpProxy) != "" {
		args = append(args, "-x", httpProxy)
	}
	args = append(args, pageURL)
	cmd := exec.CommandContext(ctx, curlBin, args...)
	var buf bytes.Buffer
	cmd.Stdout = &buf
	cmd.Stderr = &buf
	if err := cmd.Run(); err != nil {
		return "", err
	}
	return buf.String(), nil
}

func fetchColly(cfg *fetchConfig, pageURL, titleHint string) (string, string, error) {
	co := colly.NewCollector(
		colly.MaxDepth(1),
		colly.UserAgent("Mozilla/5.0 (compatible; MotorF1Crawler/1.0)"),
	)
	co.Limit(&colly.LimitRule{
		DomainGlob:  "*",
		Delay:       2 * time.Second,
		RandomDelay: time.Second,
	})

	proxyURL := strings.TrimSpace(cfg.collyHTTPProxy)
	if proxyURL == "" {
		proxyURL = strings.TrimSpace(cfg.torProxy)
	}
	if proxyURL != "" {
		pu, err := url.Parse(proxyURL)
		if err == nil {
			co.WithTransport(&http.Transport{
				Proxy: http.ProxyURL(pu),
			})
		}
	}

	var title string
	var body string
	co.OnHTML("title", func(e *colly.HTMLElement) {
		if strings.TrimSpace(title) == "" {
			title = strings.TrimSpace(e.Text)
		}
	})
	co.OnResponse(func(r *colly.Response) {
		body = string(r.Body)
	})

	if err := co.Visit(pageURL); err != nil {
		return "", titleHint, err
	}
	if strings.TrimSpace(title) == "" {
		title = titleHint
	}
	return body, title, nil
}
