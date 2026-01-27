# NYC Apartment Scraper

Automatically scrapes r/NYCapartments for new listings, filters them based on your criteria (price, neighborhood, apartment type), and adds matching listings to a Google Sheet.

## Features

- 🔄 Scrapes Reddit every 5 minutes (configurable)
- 🔍 Fuzzy matching for neighborhoods and apartment types (handles typos/variations)
- 💰 Price extraction from human-written text
- 🚫 Filters out sublets, room shares, and roommate requests
- 📊 Exports to Google Sheets with direct links
- 🔒 Deduplication - never scrapes the same post twice

## Quick Start

### 1. Install Dependencies

```bash
cd nyc-apartment-scraper
pip install -r requirements.txt
```

### 2. Set Up Google Sheets API

Follow these steps to create credentials:

#### A. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" → "New Project"
3. Name it something like "Apartment Scraper"
4. Click "Create"

#### B. Enable the Google Sheets API

1. In your project, go to "APIs & Services" → "Library"
2. Search for "Google Sheets API"
3. Click on it and click "Enable"
4. Also search for and enable "Google Drive API"

#### C. Create a Service Account

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "Service Account"
3. Name: "apartment-scraper" (or anything)
4. Click "Create and Continue"
5. Skip the optional steps, click "Done"

#### D. Download the Credentials JSON

1. Click on the service account you just created
2. Go to the "Keys" tab
3. Click "Add Key" → "Create new key"
4. Choose "JSON" and click "Create"
5. A JSON file will download - **save this as `credentials.json`** in the project folder

#### E. Create and Share Your Google Sheet

1. Create a new Google Sheet
2. Copy the Sheet ID from the URL:
   ```
   https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_HERE/edit
   ```
3. **Share the sheet with your service account email**:
   - Click "Share" in the top right
   - Find the service account email in your `credentials.json` (the `client_email` field)
   - It looks like: `apartment-scraper@your-project.iam.gserviceaccount.com`
   - Give it "Editor" access

### 3. Configure the Scraper

Edit `config.yaml`:

```yaml
# Set your price range
price:
  min: 1500
  max: 2800

# Add your Google Sheet ID
google_sheets:
  sheet_id: "YOUR_SHEET_ID_HERE"
```

Customize neighborhoods, apartment types, and exclude terms as needed.

### 4. Run the Scraper

**Test mode (no Google Sheets):**
```bash
python main.py --test
```

**Run once:**
```bash
python main.py
```

**Run continuously (every 5 minutes):**
```bash
python main.py --daemon
```

## Configuration Options

### `config.yaml` Reference

| Section | Option | Description |
|---------|--------|-------------|
| `scraping.interval_minutes` | 5 | How often to check for new posts |
| `price.min` / `price.max` | 1500-2800 | Monthly rent range in USD |
| `apartment_types` | list | Apartment types to match (fuzzy) |
| `neighborhoods` | list | NYC neighborhoods to look for (fuzzy) |
| `exclude_terms` | list | Terms that exclude a listing (sublet, etc.) |

### Fuzzy Matching

The filter uses fuzzy matching, so it will catch:
- "Williamsburg" → "wburg", "w'burg", "east williamsburg"
- "1 bedroom" → "1br", "1 bed", "one bedroom"
- "sublease" → "sublet", "sub-lease"

Add any variations to the config to improve matching.

## Output

The Google Sheet will contain:

| Column | Description |
|--------|-------------|
| Date Added | When the scraper found the listing |
| Title | Reddit post title |
| Price | Extracted price (or N/A) |
| Neighborhood | Matched neighborhood |
| Apartment Type | Matched type (studio, 1br, etc.) |
| Author | Reddit username |
| Posted Date | When the Reddit post was created |
| Link | Direct link to the Reddit post |
| Score | Reddit upvotes |
| Comments | Number of comments |
| Notes | Empty column for your notes |

## Files

```
nyc-apartment-scraper/
├── main.py           # Main entry point
├── scraper.py        # Reddit scraping logic
├── filter.py         # Fuzzy matching filter
├── sheets.py         # Google Sheets integration
├── storage.py        # Deduplication storage
├── config.yaml       # Your configuration
├── credentials.json  # Google API credentials (you create this)
├── seen_posts.json   # Tracks processed posts (auto-created)
└── requirements.txt  # Python dependencies
```

## Troubleshooting

### "Credentials file not found"
Make sure `credentials.json` is in the same folder as `main.py`.

### "Error connecting to Google Sheets"
- Make sure you shared the sheet with the service account email
- Verify the sheet ID in `config.yaml` is correct

### "No posts fetched"
- Reddit might be rate-limiting you. Wait a few minutes.
- Check your internet connection.

### Listings not matching
- Run with `--verbose` to see why posts are being filtered
- Check if neighborhoods/types are spelled correctly in config
- Lower the fuzzy threshold in `filter.py` if needed

## Tips

1. **Start broad, then narrow**: Begin with more neighborhoods and wider price range, then refine.

2. **Check the log**: Run with `--verbose` to see exactly why posts are passing/failing filters.

3. **Monitor your sheet**: Sort by "Date Added" to see newest finds first.

4. **Act fast**: Good apartments in NYC go quickly. Set up notifications on your Google Sheet!

## License

MIT - Use freely for your apartment hunt!
