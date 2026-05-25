# 🔥 Roaster Bot

Find businesses with high reputation but weak websites — ranked by revenue opportunity.

## What it does

1. Search any industry + location (e.g. "dental" + "Austin Texas")
2. Pulls top businesses from Google Maps
3. Audits each website across 8 revenue criteria
4. Ranks by opportunity score — the higher the score, the more revenue is leaking

## Scoring dimensions

| Dimension | Max Points |
|---|---|
| Page Speed | 15 |
| CTA Effectiveness | 15 |
| Trust Signals | 15 |
| Mobile Experience | 10 |
| Online Booking | 10 |
| Social Proof | 10 |
| SEO Basics | 10 |
| SSL | 5 |

**Opportunity Score** = 100 - Health Score. Higher = more opportunity.

## Setup

1. Get a free SerpApi key at [serpapi.com](https://serpapi.com)
2. Clone the repo
3. Copy `.env.example` to `.env` and add your key
4. Run: `python startup.py`
5. Open: `http://127.0.0.1:8002`

## Built with

- Python + FastAPI
- SerpApi (Google Maps)
- HTTPX for website crawling
- Vanilla JS frontend
