
# Domain Screenshoter

This tool automates taking screenshots of a list of domains while routing requests through a VPN. It manages sessions, retries on failures, and utilizes Selenium for capturing screenshots in a headless browser.

---

## Features

- **VPN Management**: Automatically connects to a random VPN configuration file from the specified directory and retries on failure.
- **Session Management**: Supports resuming previous sessions and saving retry sessions. Tracks processed domains and completed screenshots.
- **Multithreading**: Supports concurrent processing of domains with a specified number of threads.
- **Progress Tracking**: Displays progress bars for domains processed, screenshots taken, and requests made.
- **Error Logging**: Logs errors into a file in the output directory for further analysis.
- **Retry Mechanism with VPN Rotation**: If domains fail due to specific errors (e.g., timeouts), the script offers an option to retry only those domains with VPN rotation.
- **Delay Between VPN Changes**: Allows specifying a delay (in seconds) before connecting to a new VPN after disconnecting the current one.
- **Graceful Interrupt Handling**: Properly handles interruptions (e.g., Ctrl+C) during execution and input prompts, saving sessions and terminating VPN connections cleanly.

---

## Requirements

- Python 3.8+
- `requests` (for IP checking and network requests)
- `tqdm` (for progress bars)
- `selenium` (for web automation)
- `chromedriver` compatible with your Chrome version

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/domain-screenshoter.git
   cd domain-screenshoter
   ```

2. **Install the required dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure `chromedriver`:**
   - Download the appropriate version of `chromedriver` from the [official ChromeDriver repository](https://chromedriver.chromium.org/downloads) that matches your installed Chrome browser version.
   - Place the `chromedriver` executable in a directory of your choice.
   - Update the path to `chromedriver` in the `config.ini` file:
     ```ini
     [settings]
     webdriver_path = /path/to/chromedriver
     ```

---


## Usage

Run the script with the following command:
```bash
python dscreenshoter.py --vpn-dir <VPN_CONFIG_DIR> -d <DOMAIN_LIST_FILE> -s <OUTPUT_DIR> -n <MAX_REQUESTS> -t <THREADS> --timeout <TIMEOUT> -de <DELAY>
```

### Arguments:

- `--vpn-dir`: Directory containing `.ovpn` configuration files.
- `-d`, `--domains`: File containing the list of domains to process (one domain per line).
- `-s`, `--screenshot-dir`: Directory to save the screenshots.
- `-n`, `--max-requests`: Maximum number of requests to process before changing VPN.
- `-t`, `--threads`: Number of threads to use for concurrent processing.
- `--timeout`: Timeout (in seconds) for page loading in Selenium.
- `-de`, `--delay`: Delay (in seconds) before connecting to a new VPN after disconnecting the current one. Defaults to 0.

---

## Examples

### Example 1: Basic Usage

Take screenshots of domains listed in `domains.txt` with 30 threads, switching VPN after 50 requests:

```bash
python dscreenshoter.py --vpn-dir ovpn-configs -d domains.txt -s screenshots -n 50 -t 30 --timeout 10 -de 0
```

**Output:**

```
Connected to IP #1: 192.0.2.1
Domains processed / total:  50%|██████████████████████████████████████████▌                                           | 500/1000 [01:40<01:40,  5.00it/s]
Screenshots taken / total:  48%|█████████████████████████████████████████▌                                            | 480/1000 [01:40<01:44,  4.98it/s]
Requests made / total:     100%|█████████████████████████████████████████████████████████████████████████| 50/50 [01:40<00:00,  2.00s/it]

Connected to IP #2: 192.0.2.2
Domains processed / total: 100%|█████████████████████████████████████████████████████████████████████████| 1000/1000 [03:20<00:00,  5.00it/s]
Screenshots taken / total:  95%|███████████████████████████████████████████████████████████████████████   | 950/1000 [03:20<00:10,  4.98it/s]
Requests made / total:     100%|█████████████████████████████████████████████████████████████████████████| 50/50 [01:40<00:00,  2.00s/it]

All domains have been processed.
50 domains failed due to timeout errors.
Retry? (Enter 'y' to retry, 'n' to skip retry):
```

...
