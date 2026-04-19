package main

import (
	"encoding/json"
	"strings"
)

// stripSeedsLineComments elimina líneas que son solo comentarios // (JSONC ligero).
func stripSeedsLineComments(data []byte) []byte {
	lines := strings.Split(string(data), "\n")
	var b strings.Builder
	for _, line := range lines {
		t := strings.TrimSpace(line)
		if t == "" || strings.HasPrefix(t, "//") {
			continue
		}
		b.WriteString(line)
		b.WriteByte('\n')
	}
	return []byte(b.String())
}

type seedFeed struct {
	URL      string `json:"url"`
	Name     string `json:"name,omitempty"`
	Category string `json:"category,omitempty"`
	Region   string `json:"region,omitempty"`
	Lang     string `json:"lang,omitempty"`
	Priority int    `json:"priority,omitempty"`
}

func (s *seedFeed) UnmarshalJSON(b []byte) error {
	if len(b) > 0 && b[0] == '"' {
		var u string
		if err := json.Unmarshal(b, &u); err != nil {
			return err
		}
		s.URL = u
		return nil
	}
	type alias seedFeed
	return json.Unmarshal(b, (*alias)(s))
}

type seedURL struct {
	URL           string `json:"url"`
	Name          string `json:"name,omitempty"`
	Category      string `json:"category,omitempty"`
	Region        string `json:"region,omitempty"`
	Lang          string `json:"lang,omitempty"`
	Priority      int    `json:"priority,omitempty"`
	CrawlStrategy string `json:"crawl_strategy,omitempty"`
}

func (s *seedURL) UnmarshalJSON(b []byte) error {
	if len(b) > 0 && b[0] == '"' {
		var u string
		if err := json.Unmarshal(b, &u); err != nil {
			return err
		}
		s.URL = u
		return nil
	}
	type alias seedURL
	return json.Unmarshal(b, (*alias)(s))
}

type seedsFile struct {
	Version     string          `json:"version,omitempty"`
	Updated     string          `json:"updated,omitempty"`
	Description string          `json:"description,omitempty"`
	Feeds       []seedFeed      `json:"feeds"`
	URLs        []seedURL       `json:"urls"`
	Meta        json.RawMessage `json:"meta,omitempty"`
}

type seedHint struct {
	Name          string
	Category      string
	Region        string
	Lang          string
	Priority      int
	CrawlStrategy string
}

func parseSeeds(data []byte) (*seedsFile, error) {
	clean := stripSeedsLineComments(data)
	var s seedsFile
	if err := json.Unmarshal(clean, &s); err != nil {
		return nil, err
	}
	return &s, nil
}

func hintFromFeed(f *seedFeed) *seedHint {
	if f == nil {
		return nil
	}
	return &seedHint{
		Name:     f.Name,
		Category: f.Category,
		Region:   f.Region,
		Lang:     f.Lang,
		Priority: f.Priority,
	}
}

func hintFromURL(u *seedURL) *seedHint {
	if u == nil {
		return nil
	}
	return &seedHint{
		Name:          u.Name,
		Category:      u.Category,
		Region:        u.Region,
		Lang:          u.Lang,
		Priority:      u.Priority,
		CrawlStrategy: u.CrawlStrategy,
	}
}
