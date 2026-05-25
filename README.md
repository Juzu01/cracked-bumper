# cracked.st Thread Bumper

Auto-bump your threads on cracked.st using your browser cookies. No Selenium, no headless browser — just plain HTTP requests.

## Setup

1. Install dependencies:
```
pip install requests beautifulsoup4
```

2. Get your cookies:
   - Open cracked.st in Chrome and log in
   - F12 → Console → paste: `copy(document.cookie)` → Enter
   - Create `cookies.txt` next to `bumper.py`, paste and save

3. Set your search URL:
   - Go to cracked.st, search for your threads (by author = your username)
   - Copy the search results URL from the address bar
   - Open `bumper.py` and replace `YOUR_SEARCH_URL_HERE` with your URL
   - Or pass it as argument: `py bumper.py --search-url "https://cracked.st/search.php?..."`

## Usage

```bash
py bumper.py --dry-run          # test: shows threads, doesn't bump
py bumper.py                    # bump all threads
py bumper.py --delay 15         # slower (15s between bumps instead of 12s)
py bumper.py --search-url "..." # use a specific search URL
```

## How it works

1. Reads your cookies from `cookies.txt`
2. Checks you're logged in
3. Fetches your search results page(s)
4. Finds all threads with a "Bump Thread" button
5. Clicks each bump link with a delay (default 12s, server rate limit is ~10s)
6. Logs everything to `bumper.log`
7. Shows a Windows toast notification when done

## Files

| File | Description |
|------|-------------|
| `bumper.py` | Main script |
| `cookies.txt` | Your cracked.st cookies (create this) |
| `bumper.log` | Auto-generated log |

## Notes

- Cookies expire — if you get "NOT logged in", re-copy them from DevTools
- The script uses your real browser User-Agent to blend in
- Windows toast notifications work out of the box, fail silently on other OS
