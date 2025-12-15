# Domain Screenshoter
         _                                  _           _            
        | |                                | |         | |           
      __| |___  ___ _ __ ___  ___ _ __  ___| |__   ___ | |_ ___ _ __ 
     / _` / __|/ __| '__/ _ \/ _ \ '_ \/ __| '_ \ / _ \| __/ _ \ '__|
    | (_| \__ \ (__| | |  __/  __/ | | \__ \ | | | (_) | ||  __/ |   
     \__,_|___/\___|_|  \___|\___|_| |_|___/_| |_|\___/ \__\___|_|  
                                                                       
                                                                       
This tool automates taking screenshots of a list of domains, optionally routing traffic through a VPN and automatically generates an interactive HTML report for browsing, filtering, and removing visually similar duplicates using perceptual image comparison.

## Features

- **Optional VPN Rotation**: Supports OpenVPN or NordVPN (`-m, --vpn-mode`).
- **Automatic Session Management**: Saves and resumes state across runs.
- **Failure & Retry Mechanism**: Retains failed domains for later retry with IP rotation.
- **Progress Bars**: Provides real‑time feedback on processing domains, screenshots, and requests.
- **Screenshot Automation**: Uses Selenium in headless mode with full-page capture.
- **Graceful Interrupt Handling**: Safely terminates VPN connections and preserves session data.
- **Automatic Report Generation**: Creates an interactive HTML report after completion.

## Requirements

- Python 3.8+
- pip packages: `requests`, `tqdm`, `selenium`, `pillow`, `imagehash`
- Chrome + matching `chromedriver`
- OpenVPN CLI (if `-m openvpn`) or NordVPN CLI (if `-m nordvpn`)

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
  [-m {openvpn,nordvpn,none}] \\
  [-v VPN_DIR] \\
  -d DOMAINS -o OUTPUT_DIR \\
  -t THREADS -T TIMEOUT \\
  [-n MAX_REQUESTS] [-D DELAY]
```

> **Note**: `-m none` is the default. If you don't specify `-m`, the script runs without VPN.

### Arguments

| Flag | Description |
|------|-------------|
| `-m, --vpn-mode` | VPN mode: `openvpn`, `nordvpn`, or `none` (default: `none`) |
| `-v, --vpn-dir`  | Directory with `.ovpn` files (required if `-m openvpn`) |
| `-d, --domains` | File containing domains, one per line |
| `-o, --output` | Directory to store screenshots and report |
| `-t, --threads` | Number of threads for concurrent processing |
| `-T, --timeout` | Page load timeout (in seconds) for Selenium |
| `-n, --max-requests` | Requests per IP before switching VPN (required if using VPN) |
| `-D, --delay` | Delay (in seconds) before re‑establishing VPN (default: 0) |

## Sample Commands

### 1. Without VPN (default)

```bash
python dscreenshoter.py \\
    -d domains.txt \\
    -o screenshots \\
    -t 10 -T 10
```

### 2. With OpenVPN

```bash
python dscreenshoter.py \\
    -m openvpn -v /path/to/ovpn \\
    -d domains.txt -o screenshots \\
    -t 20 -T 15 -n 50 -D 5
```

### 3. With NordVPN

```bash
python dscreenshoter.py \\
    -m nordvpn \\
    -d domains.txt -o screenshots \\
    -t 20 -T 15 -n 50 -D 5
```

## Progress Bars and Sample Output

During execution, the script displays progress bars using `tqdm`. A typical console output might look like:

```
No session found for 'domains.txt_screenshots.session'. Starting a new one.
Processed domains / total:   0%|          | 0/100 [00:00<?, ?dom/s]
Screenshots OK / total:   0%|          | 0/100 [00:00<?, ?dom/s]
Requests / batch:           0%|          | 0/50  [00:00<?, ?req/s]
Connected with IP #1: 123.45.67.89
Processed domains / total:  40%|####      | 40/100 [00:15<00:22,  2.66dom/s]
...
No failed domains. Process completed.
Generating report...
Processing images: 100%|██████████| 100/100 [00:02<00:00, 45.23it/s]
Report generated at: screenshots/report.html
```

You will see:
- **Processed domains / total**: how many domains have been handled out of the total.
- **Screenshots OK / total**: how many screenshots succeeded.
- **Requests / batch**: how many requests have been performed in the current VPN batch.

When all domains are processed, or if you cancel, the current session is saved. If domains fail, you can choose to retry them with a fresh VPN connection.

## Resume & Retry

If any domains fail due to timeouts or errors, they are marked in the session file. Upon restart, you can pick up where you left off or start over. The script will also prompt you to retry failed domains at the end.

## Interactive HTML Report

The script **automatically generates** an interactive HTML report (`report.html`) in the output directory after completion. The report includes:

### Features

- **Sidebar Navigation**: List of all domains with search functionality
- **Image Gallery**: Grid view of all screenshots
- **Full-Page Screenshots**: Captures entire page content, not just viewport
- **Modal Viewer**: Click any image to view in full-screen modal
- **Keyboard Navigation**: Arrow keys to navigate, ESC to close
- **Right-Click Menu**: Exclude visually similar images
- **Lazy Loading**: Images load on-demand for better performance
- **Correct Hyperlinks**: Links use the actual URL (http/https) that worked
- **Ordered Display**: Domains shown in processing order

### Screenshots

**Main Report View:**
![Report Main View](img/screen1.png)

**Modal Image Viewer:**
![Modal Image Viewer](img/screen2.png)

### Using the Report

1. Open `report.html` in your browser
2. **Search domains**: Use the search box in the sidebar to filter domains
3. **View images**: Click any image in the gallery or sidebar to open in modal
4. **Navigate**: Use arrow keys or click arrows to browse images
5. **Exclude duplicates**: Right-click on an image and select "Exclude all matching images"
6. **Filter management**: Click "X" on filter badges to restore excluded images

The report is optimized to handle hundreds or thousands of domains efficiently with lazy loading and event delegation.


## Troubleshooting

- **VPN Issues**: Verify your VPN CLI (OpenVPN/NordVPN) is installed and configured (note: OpenVPN often requires sudo).
- **Selenium/Chromedriver**: Ensure the `chromedriver` version matches your installed Chrome.
- **Permissions**: Check write permissions for the screenshot directory.
- **Session Files**: Session data is saved in `session/`. If corrupted, remove them before re-running.
- **Report Not Generated**: If the report isn't generated automatically, you can manually run: `python generate_report.py -o <output_dir>`
