# ocado-shopper — Smart Ocado Grocery Shopper (macOS)

Reads your weekly grocery list from Apple Notes, finds the best-value product for each item on Ocado, shows a proposed basket for your approval, then adds everything to the trolley.

## What it does

1. Reads a generic weekly grocery list from an Apple Note
2. Searches Ocado for the best-value match for each item (considers deals and Ocado own-brand)
3. Detects any active deals on your list items
4. Shows the proposed basket with prices for approval
5. Adds approved items to your Ocado trolley via Playwright

## Requirements

- macOS (uses AppleScript to read from Notes)
- Playwright MCP server configured
- Ocado account (logged in, or credentials available)
- Apple Note containing your grocery list

## Usage

```
/ocado-shopper
do my Ocado shop
fill my Ocado trolley
```

You'll see a proposed basket with prices before anything is added to your trolley.
