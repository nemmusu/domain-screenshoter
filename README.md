# Domain Screenshoter
         _                                  _           _            
        | |                                | |         | |           
      __| |___  ___ _ __ ___  ___ _ __  ___| |__   ___ | |_ ___ _ __ 
     / _` / __|/ __| '__/ _ \/ _ \ '_ \/ __| '_ \ / _ \| __/ _ \ '__|
    | (_| \__ \ (__| | |  __/  __/ | | \__ \ | | | (_) | ||  __/ |   
     \__,_|___/\___|_|  \___|\___|_| |_|___/_| |_|\___/ \__\___|_|  
                                                                       
                                                                       
This tool automates taking screenshots of a list of domains — optionally routing requests through a VPN — and generates an interactive HTML report for easy browsing, filtering, and deduplication.

## Features

- **VPN Management**: Optional IP rotation via OpenVPN or NordVPN (`--vpn-mode`).
- **Session Management**: Resume interrupted runs; track processed, remaining, and failed domains.
- **Concurrency**: Multi‑threaded screenshot capture with progress bars.
- **Retry Mechanism**: Automatically retry failed domains with new IPs.
- **Interactive HTML Report**: Generate a filterable, deduplicated gallery of screenshots.
- **Graceful Interrupt Handling**: Save state and cleanly disconnect VPN on exit.

## Requirements

- Python 3.8+
- pip packages: `requests`, `tqdm`, `selenium`, `pillow`, `imagehash`
- Chrome + matching `chromedriver`
- OpenVPN CLI (if `--vpn-mode=openvpn`) or NordVPN CLI (if `--vpn-mode=nordvpn`)

## Installation

```bash
git clone https://github.com/nemmusu/domain-screenshoter.git
cd domain-screenshoter
pip install -r requirements.txt
```

Configure `chromedriver` path in `config.ini`:
```ini
[settings]
webdriver_path = /path/to/chromedriver
```

## Usage

```bash
python dscreenshoter.py \\
  --vpn-mode <openvpn|nordvpn|none> \\
  [--vpn-dir <OVPN_DIR>] \\
  -d <DOMAIN_LIST> -s <OUTPUT_DIR> \\
  [-n <MAX_REQUESTS>] -t <THREADS> \\
  [--timeout <SECONDS>] [--delay <SECONDS>]
```

> **Note**: `--vpn-mode=none` is optional. If you do not specify `--vpn-mode`, the script defaults to no VPN.

### Arguments

| Flag | Description |
|------|-------------|
| `--vpn-mode` | VPN rotation mode: `openvpn`, `nordvpn`, or `none` (default: none if not specified) |
| `--vpn-dir` | Directory containing `.ovpn` files (required if `--vpn-mode=openvpn`) |
| `-d, --domains` | File with one domain per line |
| `-s, --screenshot-dir` | Directory to save screenshots |
| `-n, --max-requests` | Requests per IP before rotating (required if using VPN) |
| `-t, --threads` | Number of concurrent threads |
| `--timeout` | Page load timeout in seconds |
| `--delay` | Delay before each VPN reconnection |

## Examples

### No VPN (single IP)
```bash
python dscreenshoter.py --vpn-mode none -d domains.txt -s screenshots -t 10 --timeout 10
```

*(Or simply omit `--vpn-mode`, as it defaults to none.)*

### OpenVPN rotation
```bash
python dscreenshoter.py --vpn-mode openvpn --vpn-dir ./ovpn-configs -d domains.txt -s screenshots -n 50 -t 20 --timeout 10 --delay 5
```

### NordVPN rotation
```bash
python dscreenshoter.py --vpn-mode nordvpn -d domains.txt -s screenshots -n 50 -t 20 --timeout 10 --delay 5
```

## Resume & Retry

If interrupted or domains time out, the script saves a session in `session/`. On restart, you can resume or start fresh. At completion, you’ll be prompted to retry failed domains.

## Generate Interactive Report

After capturing screenshots, run:
```bash
python generate_report.py -o screenshots
```
This creates `report.html` in the output folder, providing navigation, filtering, and duplicate‑image exclusion.

## Troubleshooting

- Verify VPN connectivity (`openvpn` requires `sudo`, NordVPN CLI logged in).
- Ensure `chromedriver` matches installed Chrome.
- Check file permissions and existence of paths.
- Sessions live in `session/` — delete if corrupted.