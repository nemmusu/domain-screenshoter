
# Domain Screenshot Tool with VPN

This tool automates taking screenshots of a list of domains while routing requests through a VPN. It manages sessions, retries on failures, and utilizes Selenium for capturing screenshots in a headless browser.

---

## Features

- **VPN Management**: Automatically connects to a random VPN configuration file from the specified directory and retries on failure.
- **Session Management**: Supports resuming previous sessions. Tracks processed domains and completed screenshots.
- **Multithreading**: Supports concurrent processing of domains with a specified number of threads.
- **Progress Tracking**: Displays progress bars for domains processed, screenshots taken, and requests made.
- **Error Logging**: Logs errors into a file in the output directory for further analysis.

---

## Requirements

- Python 3.8+
- `requests` (for IP checking and network requests)
- `tqdm` (for progress bars)
- `selenium` (for web automation)

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/domain-screenshot-vpn.git
   cd domain-screenshot-vpn
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Ensure you have `chromedriver` installed and configured. Update the path to `chromedriver` in the `config.ini` file.

---

## Usage

Run the script with the following command:
```bash
python dscreenshoter.py --vpn-dir <VPN_CONFIG_DIR> -d <DOMAIN_LIST_FILE> -s <OUTPUT_DIR> -n <MAX_REQUESTS> -t <THREADS> --timeout <TIMEOUT>
```

### Arguments:
- `--vpn-dir`: Directory containing `.ovpn` configuration files.
- `-d`, `--domains`: File containing the list of domains to process (one domain per line).
- `-s`, `--screenshot-dir`: Directory to save the screenshots.
- `-n`, `--max-requests`: Maximum number of requests to process before changing VPN.
- `-t`, `--threads`: Number of threads to use for concurrent processing.
- `--timeout`: Timeout (in seconds) for page loading in Selenium.

---

## Examples

### Example 1: Basic Usage
Take screenshots of domains listed in `domains.txt` with 30 threads, switching VPN after 50 requests:
```bash
python dscreenshoter.py --vpn-dir ovpn-configs -d domains.txt -s screenshots -n 50 -t 30 --timeout 10
```

### Example 2: Resume Session
If the script is interrupted, it will ask to resume the session when re-run:
```bash
python dscreenshoter.py --vpn-dir ovpn-configs -d domains.txt -s screenshots -n 50 -t 30 --timeout 10
```

Output:
```
Session found for file 'domains.txt_screenshots.session' with 100/1000 domains processed and 90 screenshots completed. Continue? (y/n)
```

### Example 3: Error Logging
Errors are logged in `error_log.txt` inside the output directory:
```
example.com: TimeoutException
testsite.org: WebDriverException
```

---

## Notes

1. **VPN Configuration**: Ensure your `.ovpn` files are configured correctly and can connect without additional inputs.
2. **Chromedriver**: Download and configure `chromedriver` compatible with your Chrome version.
3. **Permissions**: Running OpenVPN may require `sudo`. Adjust your environment accordingly.


