---
title: Free public APIs and datasets for hackathon projects
tags: data, api, dataset, public-data, free, no-account, weather, geo, science, government, finance, media
kind: data-source
---

# Free public APIs and datasets for hackathon projects

Well-known, real, freely accessible sources grouped by domain. The access line means:
`none` — callable with no key; `free key` — a key issued instantly by a form;
`account` — a login and possibly approval. Prefer `none` on the demo path so the demo
needs no login and no human dependency. Limits and terms change, so where noted check
current terms. When listing a source in an idea use the format
"name — access: none|free key|account — what it provides".

## Weather

Open-Meteo
access: none
Hourly and daily forecasts plus historical weather by latitude and longitude as JSON. Use: a forecast layer on any map or planner with no signup.

National Weather Service API (api.weather.gov)
access: none
US forecasts, alerts and station observations. Use: alerting tools; alerts are a natural trigger for a webhook-style demo.

OpenWeatherMap
access: free key
Worldwide current weather and forecasts on a free tier; check current terms. Use: a fallback when Open-Meteo lacks a field.

## Geo and maps

OpenStreetMap Nominatim
access: none
Geocoding and reverse geocoding with a usage policy requiring a user agent and low rates. Use: address-to-coordinates for a map demo; cache demo results.

Overpass API
access: none
Queries over OpenStreetMap features such as every pharmacy or bike lane in a bounding box. Use: "everything of type X near Y" ideas; precompute for the demo.

Natural Earth
access: none
Public-domain downloadable vector data for countries, coastlines and cities. Use: offline base maps with no API dependency.

## Space and science

NASA Open APIs (api.nasa.gov)
access: free key
Astronomy Picture of the Day, near-Earth objects, Mars rover photos and Earth imagery; a limited demo key exists. Use: visual demos with real imagery.

USGS Earthquake feeds
access: none
Continuously updated GeoJSON of recent earthquakes with magnitude and location. Use: live maps; the feed changes during the event, so it feels live.

Open Notify
access: none
Current International Space Station position and people in space. Use: a small, reliable live data point when a demo needs something moving.

## Knowledge

Wikipedia and MediaWiki APIs
access: none
Article search, summaries, content and page views in every language edition. Use: grounding a retrieval demo in real text with clickable citations.

Wikidata SPARQL endpoint
access: none
Structured facts about millions of entities via a query language. Use: relationship and graph ideas; precompute slow queries.

arXiv API
access: none
Search and metadata for scientific preprints with abstracts. Use: research assistants with real abstracts to retrieve over.

Open Library
access: none
Book metadata, covers and authors by ISBN or search. Use: reading tools and cover imagery.

## Code and developer

GitHub REST and GraphQL APIs
access: none
Public repositories, issues, pull requests and commits at low unauthenticated rates; a token raises limits. Use: developer tooling over a real public repo; repository webhooks are a natural inbound event.

PyPI JSON API and npm registry
access: none
Package metadata, versions and (for npm) download counts. Use: dependency analysis and supply-chain visualisation.

Stack Exchange API
access: none
Questions, answers and tags across Stack Overflow and sister sites; a free key raises quota. Use: retrieval over real developer questions.

## News and social

Hacker News API
access: none
Stories, comments and users via a public Firebase endpoint. Use: discussion and trend ideas with a constantly changing feed.

GDELT
access: none
Global news event and mention data with a document search API. Use: topic-trend maps; query narrowly, it is large.

Reddit API
access: account
Posts and comments via an OAuth application; terms and limits have changed, check current terms before relying on it.

## Government and open data

data.gov and national portals
access: none
Catalogues of government datasets (US data.gov, data.gov.uk, data.gouv.fr and many city portals). Use: finding a domain dataset in CSV or JSON in minutes.

World Bank Indicators API
access: none
Country-level development indicators over decades as JSON. Use: comparative time-series storytelling.

US Census Bureau APIs
access: free key
Demographic and economic data at many geographic levels. Use: neighbourhood context for a local-services idea.

FRED
access: free key
US and international economic time series from the Federal Reserve Bank of St. Louis. Use: economic dashboards with a twist.

Socrata city portals (SODA API)
access: none
Live city datasets such as 311 requests, permits and inspections through a common API; an app token raises limits. Use: hyper-local civic ideas with changing data.

## Health and food

Open Food Facts
access: none
Crowd-sourced product ingredients, nutrition and barcodes. Use: scan-a-barcode demos and dietary tools.

openFDA
access: none
Drug labels, adverse events, recalls and device data; a free key raises limits. Use: medication tools with real label text to retrieve over.

USDA FoodData Central
access: free key
Authoritative nutrient data for foods. Use: nutrition calculations.

## Transport

OpenSky Network
access: none
Live aircraft state vectors worldwide; an account raises limits, check current terms. Use: live flight maps.

GTFS and GTFS-Realtime feeds
access: none
Transit schedules and, for many agencies, live vehicle positions in a standard format; some agencies require registration. Use: a transit app for one city with real timetables.

GBFS bike-share feeds
access: none
Station status and bike availability for shared-mobility systems. Use: live availability maps.

## Finance

Frankfurter
access: none
Current and historical foreign-exchange reference rates. Use: currency conversion inside any tool without signup.

CoinGecko
access: none
Cryptocurrency prices and market data; a free key exists and limits have changed, check current terms. Use: price feeds for a portfolio demo.

Alpha Vantage
access: free key
Stock, forex and crypto time series on a tight free tier. Use: equities demos; cache the demo path.

## Media and culture

The Metropolitan Museum of Art Collection API
access: none
Object metadata and open-access images for hundreds of thousands of artworks. Use: visual and educational demos with striking real images.

Internet Archive APIs
access: none
Search and metadata over archived books, audio, video and web pages. Use: historical and media-retrieval ideas.

MusicBrainz
access: none
Open music metadata for artists, releases and recordings; requires a user agent and modest rates. Use: music discovery without a streaming account.

TMDB (The Movie Database)
access: free key
Film and television metadata, posters and credits. Use: recommendation twists with real posters.

Spotify Web API
access: account
Track and playlist metadata behind OAuth; playback needs a user account. Use: only when the idea centres on a user's own library.

## Datasets rather than APIs

Hugging Face Datasets
access: none
Thousands of downloadable text, image and tabular datasets; gated ones need an account. Use: labelled data for a classifier or retrieval demo.

Kaggle Datasets
access: account
Large dataset catalogue behind a free account. Use: domain data when nothing open exists; hand the download to a human early.

## Choosing sources for a demo

Pick one primary source with access `none` for the demo path and at most one
secondary source. Make one real request to each in the first hour and save the
response as a fixture so the demo survives an outage. Anything with access `account`
is a human dependency: hand it to a team member immediately or drop it.
