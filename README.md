
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
- `pillow` (for image processing)
- `imagehash` (for generating unique hashes for images)

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
- `-to`, `--timeout`: Timeout (in seconds) for page loading in Selenium.
- `-de`, `--delay`: Delay (in seconds) before connecting to a new VPN after disconnecting the current one. Defaults to 0.

---

## HTML Report Generator

### How to Use the Report Generator

After taking screenshots, you can generate an interactive HTML report of the screenshots saved in your output directory. This report allows you to browse, filter, and view screenshots interactively.

Run the following command:

```bash
python generate_report.py -o <OUTPUT_DIR>
```

- `-o`, `--output-folder`: The directory containing the screenshots for which you want to generate the report.

### Report Features

- **Interactive Gallery**: Displays all screenshots in a grid layout.
- **Image Filtering**: Allows filtering of screenshots based on unique hashes.
- **Detailed View**: Click on any screenshot to open a modal for navigation.
- **Keyboard Navigation**: Use arrow keys to navigate through images and `Esc` to close the modal.
- **Aspect Ratio Maintenance**: Ensures that screenshots retain their original proportions.
- **Context Menu**: Right-click on a screenshot to exclude similar ones from the gallery dynamically.

### Example

Generate a report for the screenshots stored in the `screenshots` directory:

```bash
python generate_report.py -o screenshots
```

This will create an `report.html` file inside the `screenshots` directory. Open it in any web browser to explore the captured screenshots.

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
Domains processed / total:  50%|██████████████████████████████████████████▌                                           | 500/1000 [01:40<01:40,  5.00dom/s]
Screenshots taken / total:  48%|█████████████████████████████████████████▌                                            | 480/1000 [01:40<01:44,  4.98dom/s]
Requests made / total:     100%|█████████████████████████████████████████████████████████████████████████| 50/50 [01:40<00:00,  2.00s/it]

Connected to IP #2: 192.0.2.2
Domains processed / total: 100%|█████████████████████████████████████████████████████████████████████████| 1000/1000 [03:20<00:00,  5.00dom/s]
Screenshots taken / total:  95%|███████████████████████████████████████████████████████████████████████   | 950/1000 [03:20<00:10,  4.98dom/s]
Requests made / total:     100%|█████████████████████████████████████████████████████████████████████████| 50/50 [01:40<00:00,  2.00s/dom]

All domains have been processed.
50 domains failed due to timeout errors.
Retry? (Enter 'y' to retry, 'n' to skip retry):
```

### Example 2: Resume Session

If the script is interrupted, it will ask to resume the session when re-run:

```bash
python dscreenshoter.py --vpn-dir ovpn-configs -d domains.txt -s screenshots -n 50 -t 30 --timeout 10 -de 0
```

**Output:**

```
Session found for file 'domains.txt_screenshots.session' with 500/1000 domains processed and 480 screenshots completed.
Continue? (Enter 'y' to continue, 'n' to start a new session):
```

- **To continue the session:** Enter `y` and press **Enter**.
- **To start a new session:** Enter `n` and press **Enter**.

### Example 3: Retry Failed Domains with VPN Rotation

At the end of a session, the script identifies domains that failed due to specific errors (e.g., timeouts) and offers an option to retry with VPN rotation:

```bash
50 domains failed due to timeout errors.
Retry? (Enter 'y' to retry, 'n' to skip retry):
```

**If you choose `y`, the script processes only the failed domains, connecting to a new VPN before each batch.**

**Output during retry:**

```
Retrying domains / total: 100%|███████████████████████████████████████████████████████████████████████████| 50/50 [01:45<00:00,  2.00s/dom]
Screenshots taken / total:  80%|████████████████████████████████████████████████████████                   | 40/50 [01:45<00:26,  2.60s/dom]
Requests made / total:     100%|█████████████████████████████████████████████████████████████████████████| 50/50 [01:40<00:00,  2.00s/dom]
Connected to IP #1: 192.0.2.3

Retry completed. 50 domains processed, 40 screenshots taken, 10 domains still failed.
10 domains still failed after retry.
```

**Resuming Retry:**

If the retry process is interrupted, you can resume it:

```bash
Retry session found with 20 domains to process.
Processed 30/50 domains, 25 screenshots taken.
Continue? (Enter 'y' to continue, 'n' to start a new session):
```


### Example 4: Graceful Interrupt Handling

You can interrupt the script at any point using **Ctrl+C**. The script will handle the interruption.

### Example 5: Add Delay Between VPN Changes

Add a 5-second delay between VPN disconnection and reconnection:

```bash
python dscreenshoter.py --vpn-dir ovpn-configs -d domains.txt -s screenshots -n 50 -t 30 --timeout 10 -de 5
```

### Example 6: Error Logging

Errors are logged in `error_log.txt` inside the output directory:

```
example.com: timeout: Timed out receiving message from renderer
testsite.org: Unexpected error during screenshot.
```

---

## Notes

1. **VPN Configuration:**
   - Ensure your `.ovpn` files are configured correctly and can connect without additional inputs.
   - The script selects a random VPN configuration from the provided directory for each VPN connection.
   - Running OpenVPN may require `sudo` privileges. Adjust your environment accordingly.

2. **Chromedriver:**
   - Download and configure `chromedriver` compatible with your Chrome version from the [official ChromeDriver repository](https://chromedriver.chromium.org/downloads).
   - Update the `webdriver_path` in the `config.ini` file to point to your `chromedriver` executable.

3. **Permissions:**
   - The script may require elevated permissions to manage VPN connections. Run the script with appropriate permissions.

4. **Session Files:**
   - The script creates session files named `<domain_file>_<screenshot_dir>.session` to track progress.
   - Retry sessions are saved with the extension `.retry.session`.

5. **VPN Rotation During Retry:**
   - During retries, the script connects to a new VPN before processing each batch of failed domains, increasing the chances of successful connections.

---

## Troubleshooting

- **VPN Connection Issues:**
  - If the script fails to connect to the VPN, ensure that your VPN configurations are correct and that you have network connectivity.
  - Check that OpenVPN is installed and accessible from the command line.

- **Selenium Errors:**
  - Ensure that `chromedriver` is installed and matches the version of your Chrome browser.
  - Verify that the `webdriver_path` in `config.ini` is correct.

- **Permission Denied Errors:**
  - Running VPN connections and Selenium may require elevated permissions.
  - Consider running the script with `sudo` if necessary, but be cautious with permissions.

