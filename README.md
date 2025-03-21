# Domain Screenshoter
         _                                  _           _            
        | |                                | |         | |           
      __| |___  ___ _ __ ___  ___ _ __  ___| |__   ___ | |_ ___ _ __ 
     / _` / __|/ __| '__/ _ \/ _ \ '_ \/ __| '_ \ / _ \| __/ _ \ '__|
    | (_| \__ \ (__| | |  __/  __/ | | \__ \ | | | (_) | ||  __/ |   
     \__,_|___/\___|_|  \___|\___|_| |_|___/_| |_|\___/ \__\___|_|  
                                                                       
                                                                       
This tool automates taking screenshots of a list of domains — optionally routing traffic through a VPN — and generates an interactive HTML report for browsing, filtering, and removing visually similar duplicates using perceptual image comparison.

## Features

- **Optional VPN Rotation**: Supports OpenVPN or NordVPN (`--vpn-mode`).
- **Automatic Session Management**: Saves and resumes state across runs.
- **Failure & Retry Mechanism**: Retains failed domains for later retry with IP rotation.
- **Progress Bars**: Provides real‑time feedback on processing domains, screenshots, and requests.
- **Screenshot Automation**: Uses Selenium in headless mode with optional SSL bypass.
- **Graceful Interrupt Handling**: Safely terminates VPN connections and preserves session data.

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

Ensure `chromedriver` is configured in `config.ini`:

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
| `--vpn-mode` | VPN mode: `openvpn`, `nordvpn`, or `none` (defaults to none if not specified) |
| `--vpn-dir`  | Directory with `.ovpn` files (required if `--vpn-mode=openvpn`) |
| `-d, --domains` | File containing domains, one per line |
| `-s, --screenshot-dir` | Directory to store screenshots |
| `-n, --max-requests` | Requests per IP before switching VPN (required if using VPN) |
| `-t, --threads` | Number of threads for concurrent processing |
| `--timeout` | Page load timeout (in seconds) for Selenium |
| `--delay` | Delay (in seconds) before re‑establishing VPN |

## Sample Commands

### 1. Without VPN

```bash
python dscreenshoter.py --vpn-mode none \\
    -d domains.txt \\
    -s screenshots \\
    -t 10 --timeout 10
```
*(Or simply omit `--vpn-mode`, as it defaults to none.)*

### 2. With OpenVPN

```bash
python dscreenshoter.py --vpn-mode openvpn --vpn-dir /path/to/ovpn \\
    -d domains.txt -s screenshots \\
    -n 50 -t 20 --timeout 15 --delay 5
```

### 3. With NordVPN

```bash
python dscreenshoter.py --vpn-mode nordvpn \\
    -d domains.txt \\
    -s screenshots \\
    -n 50 -t 20 --timeout 15 --delay 5
```

## Progress Bars and Sample Output

During execution, the script displays progress bars using `tqdm`. A typical console output might look like:

```
No session found for 'domains.txt_screenshots.session'. Starting a new one.
Processed domains / total:   0%|          | 0/100 [00:00<?, ?dom/s]
Screenshots done / total:   0%|          | 0/100 [00:00<?, ?dom/s]
Requests / total:           0%|          | 0/50  [00:00<?, ?dom/s]
Connected with IP #1: 123.45.67.89
Processed domains / total:  40%|####      | 40/100 [00:15<00:22,  2.66dom/s]
...
Processing completed.
60 domains failed.
Retry? (y/n):
```

You will see:
- **Processed domains / total**: how many domains have been handled out of the total.
- **Screenshots done / total**: how many screenshots succeeded.
- **Requests / total**: how many requests have been performed in the current VPN batch.

When all domains are processed, or if you cancel, the current session is saved. If domains fail, you can choose to retry them with a fresh VPN connection.

## Resume & Retry

If any domains fail due to timeouts or errors, they are marked in the session file. Upon restart, you can pick up where you left off or start over. The script will also prompt you to retry failed domains at the end.

## Generate Interactive Report

After the script finishes capturing screenshots:

```bash
python generate_report.py -o screenshots
```

This creates a `report.html` inside the `screenshots` folder, allowing you to:
- Browse all screenshots.
- Filter and group them.
- Identifies and eliminates near-duplicate screenshots based on visual similarity.

## Troubleshooting

- **VPN Issues**: Verify your VPN CLI (OpenVPN/NordVPN) is installed and configured (note: OpenVPN often requires sudo).
- **Selenium/Chromedriver**: Ensure the `chromedriver` version matches your installed Chrome.
- **Permissions**: Check write permissions for the screenshot directory.
- **Session Files**: Session data is saved in `session/`. If corrupted, remove them before re-running.

