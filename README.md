# Domain Screenshoter

         _                                  _           _            
        | |                                | |         | |           
      __| |___  ___ _ __ ___  ___ _ __  ___| |__   ___ | |_ ___ _ __ 
     / _` / __|/ __| '__/ _ \/ _ \ '_ \/ __| '_ \ / _ \| __/ _ \ '__|
    | (_| \__ \ (__| | |  __/  __/ | | \__ \ | | | (_) | ||  __/ |   
     \__,_|___/\___|_|  \___|\___|_| |_|___/_| |_|\___/ \__\___|_|   
                                                                     
                                                                     
This tool automates taking screenshots of a list of domains while routing requests through a VPN. It supports both NordVPN and OpenVPN, manages sessions, retries failed requests, and utilizes Selenium for capturing screenshots in a headless browser.

---

## Features

- **VPN Management**: Supports both NordVPN and OpenVPN for routing requests.
- **Session Management**: Resumes previous sessions and tracks processed domains.
- **Multithreading**: Runs multiple requests concurrently for efficiency.
- **Progress Tracking**: Displays progress bars for requests, screenshots, and domains processed.
- **Retry Mechanism with VPN Rotation**: Retries failed domains with automatic VPN changes.
- **Graceful Interrupt Handling**: Saves session state and terminates VPN connections safely on exit.
- **Report Generator**: Creates an interactive HTML report of screenshots for easy browsing.

---

## Requirements

- Python 3.8+
- `requests`, `tqdm`, `selenium`
- `chromedriver` (matching your Chrome version)
- OpenVPN or NordVPN CLI

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/domain-screenshoter.git
   cd domain-screenshoter
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure `chromedriver`:
   ```ini
   [settings]
   webdriver_path = /path/to/chromedriver
   ```

---

## Usage

Run the script with:
```bash
python dscreenshoter.py [-d <DOMAIN_LIST>] [-s <OUTPUT_DIR>] [-n <MAX_REQUESTS>] [-t <THREADS>] [--timeout <TIMEOUT>] [--ovpn-dir <VPN_DIR> | --use-nordvpn] [-de <DELAY>]
```

### Arguments:

- `-d, --domains`: File containing the list of domains.
- `-s, --screenshot-dir`: Directory to save screenshots.
- `-n, --max-requests`: Requests before changing VPN.
- `-t, --threads`: Number of concurrent threads.
- `--timeout`: Page load timeout.
- `-de, --delay`: Delay before VPN change.
- `--ovpn-dir`: OpenVPN `.ovpn` directory (if using OpenVPN).
- `--use-nordvpn`: Use NordVPN instead of OpenVPN.

---

## Examples

### 1. Using OpenVPN
```bash
python dscreenshoter.py --ovpn-dir ovpn-configs -d domains.txt -s screenshots -n 50 -t 30 --timeout 10 -de 5
```

### 2. Using NordVPN
```bash
python dscreenshoter.py --use-nordvpn -d domains.txt -s screenshots -n 50 -t 30 --timeout 10 -de 5
```

### 3. Resume Previous Session
```bash
python dscreenshoter.py --ovpn-dir ovpn-configs -d domains.txt -s screenshots -n 50 -t 30 --timeout 10 -de 5
```
If an interrupted session is detected, the script prompts to resume or start fresh.

### 4. Retry Failed Domains with VPN Rotation
At the end, if domains failed, the script offers:
```bash
50 domains failed due to timeouts.
Retry? (y/n)
```
If `y` is chosen, only failed domains are retried with VPN rotation.

### 5. Generate HTML Report
```bash
python generate_report.py -o screenshots
```
This creates `report.html`, allowing interactive browsing of screenshots.

---

## Notes

- Ensure VPN configurations work before running.
- `chromedriver` must match your Chrome version.
- OpenVPN may require `sudo`.

---

## Troubleshooting

- **VPN Issues**: Check OpenVPN/NordVPN connectivity.
- **Selenium Errors**: Verify `chromedriver` installation.
- **Permissions**: Use appropriate user privileges.
- **Session Files**: Sessions are saved in `session/` and can be resumed later.
