import os
import sys
import time
import random
import argparse
import configparser
import requests
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from concurrent.futures import ThreadPoolExecutor, as_completed, FIRST_COMPLETED, wait
import subprocess
import logging
import json

def banner():
    print("""     _                                  _           _            
        | |                                | |         | |           
      __| |___  ___ _ __ ___  ___ _ __  ___| |__   ___ | |_ ___ _ __ 
     / _` / __|/ __| '__/ _ \/ _ \ '_ \/ __| '_ \ / _ \| __/ _ \ '__|
    | (_| \__ \ (__| | |  __/  __/ | | \__ \ | | | (_) | ||  __/ |   
     \__,_|___/\___|_|  \___|\___|_| |_|___/_| |_|\___/ \__\___|_|   
                                                                     
                                                                     """)

def parse_error_log(log_file, target_error="timeout: Timed out receiving message from renderer"):
    if not os.path.exists(log_file):
        return []
    failed_domains = set()
    try:
        with open(log_file, "r") as f:
            for line in f:
                if target_error in line:
                    domain = line.split(":")[0].strip()
                    failed_domains.add(domain)
    except Exception:
        logging.getLogger('general_errors').error(f"Failed to parse error log '{log_file}'.")
    return list(failed_domains)

def save_retry_session(retry_file, processed_domains, remaining_domains, screenshots_done, failed_domains):
    session_dir = ensure_session_dir()
    retry_path = os.path.join(session_dir, retry_file)
    retry_data = {
        "processed_domains": processed_domains,
        "remaining_domains": remaining_domains,
        "screenshots_done": screenshots_done,
        "failed_domains": failed_domains,
    }
    try:
        with open(retry_path, "w") as f:
            json.dump(retry_data, f)
    except Exception as e:
        logging.getLogger('general_errors').error(f"Failed to save retry session to '{retry_path}': {str(e)}")

def load_retry_session(retry_file):
    session_dir = ensure_session_dir()
    retry_path = os.path.join(session_dir, retry_file)
    if os.path.exists(retry_path):
        try:
            with open(retry_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.getLogger('general_errors').error(f"Failed to load retry session from '{retry_path}': {str(e)}")
    return {}

def retry_failed_domains(session_file, output_folder, vpn_dir, max_requests, threads, timeout, webdriver_path, delay):
    retry_file = f"{os.path.basename(session_file)}.retry.session"
    log_file = os.path.join(output_folder, "error_log.txt")

    retry_session = load_retry_session(retry_file)
    if retry_session:
        remaining_domains = retry_session.get("remaining_domains", [])
        processed_domains = retry_session.get("processed_domains", [])
        screenshots_done = retry_session.get("screenshots_done", 0)
        failed_domains_set = set(retry_session.get("failed_domains", []))
        total_domains = len(remaining_domains) + len(processed_domains)
        print(f"Retry session found with {len(remaining_domains)} domains to process.")
        print(f"Processed {len(processed_domains)}/{total_domains} domains, {screenshots_done} screenshots taken.")
        while True:
            try:
                print("Continue? (Enter 'y' to continue, 'n' to start a new session):")
                choice = input().strip().lower()
                if choice == 'y':
                    break
                elif choice == 'n':
                    os.remove(retry_file)
                    return
                else:
                    print("Invalid input. Please enter 'y' or 'n'.")
            except KeyboardInterrupt:
                print("\nOperation cancelled by user.")
                sys.exit(0)
    else:
        session = load_session(session_file)
        if not session or "failed_domains" not in session or not session["failed_domains"]:
            print("No failed domains to retry.")
            return
        remaining_domains = list(set(session["failed_domains"]))
        processed_domains = []
        screenshots_done = 0
        failed_domains_set = set()
        total_domains = len(remaining_domains)
        print(f"{len(remaining_domains)} domains failed due to timeout errors. Retrying with IP rotation.")

    progress_bar_domains = tqdm(total=total_domains, desc="Retrying domains / total", position=0, unit="dom")
    progress_bar_screenshots = tqdm(total=total_domains, desc="Screenshots taken / total", position=1, unit="dom")
    progress_bar_requests = tqdm(total=max_requests, desc="Requests made / total", position=2, unit="dom")
    progress_bar_domains.update(len(processed_domains))
    progress_bar_screenshots.update(screenshots_done)

    vpn_process = None
    ip_counter = 0

    with ThreadPoolExecutor(max_workers=threads) as executor:
        for i in range(0, len(remaining_domains), max_requests):
            connection_attempts = 0
            connected = False
            while not connected and connection_attempts < 5:
                if vpn_process:
                    try:
                        vpn_process.terminate()
                        vpn_process.wait(timeout=5)
                    except Exception:
                        logging.getLogger('general_errors').error("Failed to terminate VPN process.")
                vpn_process = connect_vpn(vpn_dir)
                if vpn_process is None:
                    connection_attempts += 1
                    continue
                current_ip = wait_for_vpn_connection()
                if current_ip:
                    connected = True
                    ip_counter += 1
                    tqdm.write(f"Connected to IP #{ip_counter}: {current_ip}")
                else:
                    tqdm.write("VPN connection failed. Retrying...")
                    connection_attempts += 1
            if not connected:
                tqdm.write("Failed to connect to any VPN after 5 attempts. Saving retry session and exiting...")
                save_retry_session(retry_file, processed_domains, remaining_domains[i:], screenshots_done, list(failed_domains_set))
                if vpn_process:
                    try:
                        vpn_process.terminate()
                    except Exception:
                        logging.getLogger('general_errors').error("Failed to terminate VPN process during exit.")
                sys.exit(1)

            batch_domains = remaining_domains[i : i + max_requests]
            progress_bar_requests.reset()
            completed_requests = 0

            futures = {
                executor.submit(take_screenshot, domain, output_folder, timeout, webdriver_path): domain
                for domain in batch_domains.copy()
            }
            try:
                for future in as_completed(futures):
                    domain = futures[future]
                    remaining_domains.remove(domain)
                    try:
                        success = future.result()
                        processed_domains.append(domain)
                        progress_bar_domains.update(1)
                        progress_bar_requests.update(1)
                        completed_requests += 1
                        if success:
                            screenshots_done += 1
                            progress_bar_screenshots.update(1)
                            failed_domains_set.discard(domain)
                        else:
                            failed_domains_set.add(domain)
                    except Exception:
                        logging.getLogger('domain_errors').error(f"{domain}: Unexpected error during retry.")
                        failed_domains_set.add(domain)
            except KeyboardInterrupt:
                print("\nInterrupted during retry. Saving retry session...")
                save_retry_session(
                    retry_file,
                    processed_domains,
                    remaining_domains[i + completed_requests:],
                    screenshots_done,
                    list(failed_domains_set)
                )
                if vpn_process:
                    try:
                        vpn_process.terminate()
                    except Exception:
                        logging.getLogger('general_errors').error("Failed to terminate VPN process during interrupt.")
                print(f"Retry session saved as '{retry_file}'. You can resume it later.")
                sys.exit(0)
            finally:
                # Save the session after each batch
                save_retry_session(
                    retry_file,
                    processed_domains,
                    remaining_domains[i + completed_requests:],
                    screenshots_done,
                    list(failed_domains_set)
                )

            if vpn_process:
                try:
                    vpn_process.terminate()
                except Exception:
                    logging.getLogger('general_errors').error("Failed to terminate VPN process during retry.")

    progress_bar_domains.close()
    progress_bar_screenshots.close()
    progress_bar_requests.close()

    main_session = load_session(session_file)
    if main_session:
        main_session['failed_domains'] = list(failed_domains_set)
        save_session(session_file, main_session.get('processed_domains', []), main_session.get('remaining_domains', []), main_session.get('screenshots_done', 0), failed_domains_set)
    else:
        save_session(session_file, [], [], 0, failed_domains_set)

    if failed_domains_set:
        try:
            with open(log_file, "w") as log:
                for domain in failed_domains_set:
                    log.write(f"{domain}: timeout: Timed out receiving message from renderer\n")
        except Exception:
            logging.getLogger('general_errors').error(f"Failed to write failed domains to '{log_file}'.")
    else:
        if os.path.exists(log_file):
            os.remove(log_file)

    if os.path.exists(retry_file):
        os.remove(retry_file)

    print(f"Retry completed. {len(processed_domains)} domains processed, {screenshots_done} screenshots taken, {len(failed_domains_set)} domains still failed.")

def validate_session(domains, screenshot_dir, session):
    processed_domains = session.get("processed_domains", [])
    screenshots_done = session.get("screenshots_done", 0)
    failed_domains = session.get("failed_domains", [])

    # Remove duplicates from processed_domains and failed_domains
    processed_domains = list(set(processed_domains))
    failed_domains = set(failed_domains)

    # Ensure processed_domains and failed_domains only include domains from the original list
    domains_set = set(domains)
    processed_domains = list(domains_set.intersection(processed_domains))
    failed_domains = domains_set.intersection(failed_domains)

    actual_screenshots = len([f for f in os.listdir(screenshot_dir) if f.endswith(".png")])
    screenshots_done = actual_screenshots

    return processed_domains, screenshots_done, failed_domains

def setup_logging(output_folder):
    error_log_file = os.path.join(output_folder, "error_log.txt")
    ds_error_log_file = os.path.join(output_folder, "ds_errors.txt")

    domain_logger = logging.getLogger('domain_errors')
    domain_logger.setLevel(logging.ERROR)
    domain_handler = logging.FileHandler(error_log_file)
    domain_handler.setLevel(logging.ERROR)
    domain_formatter = logging.Formatter("%(message)s")
    domain_handler.setFormatter(domain_formatter)
    domain_logger.addHandler(domain_handler)
    domain_logger.propagate = False

    general_logger = logging.getLogger('general_errors')
    general_logger.setLevel(logging.ERROR)
    general_handler = logging.FileHandler(ds_error_log_file)
    general_handler.setLevel(logging.ERROR)
    general_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    general_handler.setFormatter(general_formatter)
    general_logger.addHandler(general_handler)
    general_logger.propagate = False

def get_webdriver_path(config_file="config.ini"):
    config = configparser.ConfigParser()
    if not os.path.exists(config_file):
        logging.getLogger('general_errors').error(f"Configuration file '{config_file}' not found.")
        raise FileNotFoundError(f"Configuration file '{config_file}' not found.")
    config.read(config_file)
    if not config.has_section("settings"):
        logging.getLogger('general_errors').error("Missing 'settings' section in config.ini.")
        raise ValueError("Missing 'settings' section in config.ini.")
    webdriver_path = config.get("settings", "webdriver_path", fallback=None)
    if not webdriver_path or not os.path.exists(webdriver_path):
        logging.getLogger('general_errors').error("WebDriver path not found in config.ini.")
        raise FileNotFoundError("WebDriver path not found in config.ini.")
    return webdriver_path

def connect_vpn(vpn_dir):
    try:
        ovpn_files = [f for f in os.listdir(vpn_dir) if f.endswith(".ovpn")]
        if not ovpn_files:
            raise FileNotFoundError("No VPN configuration files found in the VPN directory.")
        ovpn_file = random.choice(ovpn_files)
        ovpn_path = os.path.join(vpn_dir, ovpn_file)
        vpn_process = subprocess.Popen(
            ["sudo", "openvpn", "--config", ovpn_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return vpn_process
    except Exception as e:
        logging.getLogger('general_errors').error(f"VPN connection error: {str(e)}")
        return None

def get_current_ip():
    try:
        response = requests.get("https://ifconfig.me", timeout=10)
        return response.text.strip()
    except requests.RequestException:
        return "IP unavailable"

def wait_for_vpn_connection(timeout=30):
    start_time = time.time()
    initial_ip = get_current_ip()
    while time.time() - start_time < timeout:
        current_ip = get_current_ip()
        if current_ip != initial_ip and current_ip != "IP unavailable":
            return current_ip
        time.sleep(2)
    return None

def take_screenshot(domain, output_folder, timeout, webdriver_path):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    try:
        service = Service(webdriver_path)
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        logging.getLogger('general_errors').error(f"{domain}: WebDriver initialization failed.")
        return False
    try:
        url = f"http://{domain}"
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        screenshot_path = os.path.join(output_folder, f"{domain}.png")
        driver.save_screenshot(screenshot_path)
        return os.path.exists(screenshot_path)
    except (WebDriverException, TimeoutException):
        logging.getLogger('domain_errors').error(f"{domain}: timeout: Timed out receiving message from renderer")
        return False
    except Exception:
        logging.getLogger('domain_errors').error(f"{domain}: Unexpected error during screenshot.")
        return False
    finally:
        driver.quit()

def ensure_session_dir():
    session_dir = "session"
    os.makedirs(session_dir, exist_ok=True)
    return session_dir

def save_on_interrupt(session_file, processed_domains, remaining_domains, screenshots_done, failed_domains, retry=False):
    try:
        if retry:
            save_retry_session(session_file, processed_domains, remaining_domains, screenshots_done, list(failed_domains))
        else:
            save_session(session_file, processed_domains, remaining_domains, screenshots_done, failed_domains)
    except Exception as e:
        logging.getLogger('general_errors').error(f"Failed to save session on interrupt: {str(e)}")

def save_session(session_file, processed_domains, remaining_domains, screenshots_done, failed_domains):
    session_dir = ensure_session_dir()
    session_path = os.path.join(session_dir, session_file)
    session_data = {
        "processed_domains": processed_domains,
        "remaining_domains": remaining_domains,
        "screenshots_done": screenshots_done,
        "failed_domains": list(failed_domains),
    }
    try:
        with open(session_path, "w") as f:
            json.dump(session_data, f)
    except Exception as e:
        logging.getLogger('general_errors').error(f"Failed to save session to '{session_path}': {str(e)}")

def load_session(session_file):
    session_dir = ensure_session_dir()
    session_path = os.path.join(session_dir, session_file)
    if os.path.exists(session_path):
        try:
            with open(session_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.getLogger('general_errors').error(f"Failed to load session from '{session_path}': {str(e)}")
    return {}

def process_domains(domains, output_folder, vpn_dir, max_requests, threads, timeout, webdriver_path, session_file, delay):
    vpn_process = None

    # Remove duplicates from domains list
    domains = list(set(domains))

    processed_domains = []
    screenshots_done = 0
    failed_domains = set()
    log_file = os.path.join(output_folder, "error_log.txt")

    session = load_session(session_file)
    if session:
        # Remove duplicates from session data and ensure consistency
        processed_domains, screenshots_done, failed_domains = validate_session(domains, output_folder, session)
        print(f"Session found for file '{os.path.basename(session_file)}' with {len(processed_domains)}/{len(domains)} domains processed and {screenshots_done} screenshots completed.")
        while True:
            try:
                print("Continue? (Enter 'y' to continue, 'n' to start a new session):")
                choice = input().strip().lower()
                if choice == 'y':
                    break
                elif choice == 'n':
                    try:
                        os.remove(os.path.join("session", session_file))
                    except Exception:
                        logging.getLogger('general_errors').error(f"Failed to remove session file '{session_file}'.")
                    processed_domains, screenshots_done, failed_domains = [], 0, set()
                    break
                else:
                    print("Invalid input. Please enter 'y' or 'n'.")
            except KeyboardInterrupt:
                print("\nOperation cancelled by user.")
                sys.exit(0)
    else:
        print(f"No session found for file '{os.path.basename(session_file)}'. Starting new session.")
        processed_domains, screenshots_done, failed_domains = [], 0, set()

    # Recompute remaining_domains accurately
    remaining_domains = [d for d in domains if d not in processed_domains and d not in failed_domains]

    if remaining_domains:
        progress_bar_domains = tqdm(total=len(domains), desc="Domains processed / total", position=0, unit="dom")
        progress_bar_screenshots = tqdm(total=len(domains), desc="Screenshots taken / total", position=1, unit="dom")
        progress_bar_requests = tqdm(total=max_requests, desc="Requests made / total", position=2, unit="dom")
        progress_bar_domains.update(len(processed_domains) + len(failed_domains))
        progress_bar_screenshots.update(screenshots_done)

        ip_counter = 0

        with ThreadPoolExecutor(max_workers=threads) as executor:
            for i in range(0, len(remaining_domains), max_requests):
                connection_attempts = 0
                connected = False
                while not connected and connection_attempts < 5:
                    if vpn_process:
                        try:
                            vpn_process.terminate()
                            vpn_process.wait(timeout=5)
                        except Exception:
                            logging.getLogger('general_errors').error("Failed to terminate VPN process.")
                    vpn_process = connect_vpn(vpn_dir)
                    if vpn_process is None:
                        connection_attempts += 1
                        continue
                    current_ip = wait_for_vpn_connection()
                    if current_ip:
                        connected = True
                        ip_counter += 1
                        tqdm.write(f"Connected to IP #{ip_counter}: {current_ip}")
                    else:
                        tqdm.write("VPN connection failed. Retrying...")
                        connection_attempts += 1
                if not connected:
                    tqdm.write("Failed to connect to any VPN after 5 attempts. Saving session and exiting...")
                    save_session(session_file, processed_domains, remaining_domains[i:], screenshots_done, failed_domains)
                    if vpn_process:
                        try:
                            vpn_process.terminate()
                        except Exception:
                            logging.getLogger('general_errors').error("Failed to terminate VPN process during exit.")
                    sys.exit(1)

                batch_domains = remaining_domains[i : i + max_requests]
                progress_bar_requests.reset()
                completed_requests = 0
                interrupted = False

                futures = {
                    executor.submit(take_screenshot, domain, output_folder, timeout, webdriver_path): domain
                    for domain in batch_domains
                }
                try:
                    for future in as_completed(futures):
                        domain = futures[future]
                        try:
                            success = future.result()
                            completed_requests += 1
                            progress_bar_requests.update(1)
                            progress_bar_domains.update(1)
                            processed_domains.append(domain)
                            if success:
                                screenshots_done += 1
                                progress_bar_screenshots.update(1)
                            else:
                                failed_domains.add(domain)
                        except Exception:
                            logging.getLogger('domain_errors').error(f"{domain}: Unexpected error during processing.")
                            failed_domains.add(domain)
                except KeyboardInterrupt:
                    interrupted = True
                finally:
                    # Save the session after each batch or interrupt
                    save_session(session_file, processed_domains, remaining_domains[i + completed_requests:], screenshots_done, failed_domains)
                    if interrupted:
                        tqdm.write(f"\nOperation cancelled by user. Session saved as '{session_file}'.")
                        if vpn_process:
                            try:
                                vpn_process.terminate()
                            except Exception:
                                logging.getLogger('general_errors').error("Failed to terminate VPN process during interrupt.")
                        sys.exit(0)

                if vpn_process:
                    try:
                        vpn_process.terminate()
                    except Exception:
                        logging.getLogger('general_errors').error("Failed to terminate VPN process after batch.")

        if vpn_process:
            try:
                vpn_process.terminate()
            except Exception:
                logging.getLogger('general_errors').error("Failed to terminate VPN process at the end.")

        save_session(session_file, processed_domains, [], screenshots_done, failed_domains)
        progress_bar_domains.close()
        progress_bar_screenshots.close()
        progress_bar_requests.close()
    else:
        print("All domains have been processed.")

    if failed_domains:
        print(f"{len(failed_domains)} domains failed due to timeout errors.")
        while True:
            try:
                print("Retry? (Enter 'y' to retry, 'n' to skip retry):")
                retry_choice = input().strip().lower()
                if retry_choice == 'y':
                    retry_failed_domains(session_file, output_folder, vpn_dir, max_requests, threads, timeout, webdriver_path, delay)
                    session = load_session(session_file)
                    failed_domains = set(session.get("failed_domains", []))
                    if failed_domains:
                        print(f"{len(failed_domains)} domains still failed after retry.")
                    else:
                        print("All domains have been successfully processed after retry.")
                    break
                elif retry_choice == 'n':
                    print("Retry skipped.")
                    break
                else:
                    print("Invalid input. Please enter 'y' or 'n'.")
            except KeyboardInterrupt:
                print("\nOperation cancelled by user.")
                sys.exit(0)
    else:
        print("No failed domains to retry.")

def main():
    banner()
    parser = argparse.ArgumentParser(description="Domain screenshot tool with VPN rotation.")
    parser.add_argument("--vpn-dir", required=True, help="Folder with VPN configuration files.")
    parser.add_argument("-d", "--domains", required=True, help="File with the list of domains to process.")
    parser.add_argument("-s", "--screenshot-dir", required=True, help="Folder to save screenshots.")
    parser.add_argument("-n", "--max-requests", type=int, required=True, help="Max requests before changing VPN.")
    parser.add_argument("-t", "--threads", type=int, required=True, help="Number of threads to use.")
    parser.add_argument("-to", "--timeout", type=int, required=True, help="Page load timeout.")
    parser.add_argument("-de", "--delay", type=int, default=0, help="Delay in seconds before connecting to a new VPN.")
    args = parser.parse_args()

    try:
        if not os.path.exists(args.vpn_dir):
            error_message = f"VPN directory '{args.vpn_dir}' does not exist."
            print(f"Error: {error_message}")
            logging.getLogger('general_errors').error(error_message)
            sys.exit(1)
        ovpn_files = [f for f in os.listdir(args.vpn_dir) if f.endswith(".ovpn")]
        if not ovpn_files:
            error_message = f"No VPN configuration files found in '{args.vpn_dir}'."
            print(f"Error: {error_message}")
            logging.getLogger('general_errors').error(error_message)
            sys.exit(1)
    except Exception as e:
        error_message = f"Error accessing VPN directory: {str(e)}"
        print(f"Error: {error_message}")
        logging.getLogger('general_errors').error(error_message)
        sys.exit(1)

    try:
        webdriver_path = get_webdriver_path()
    except Exception as e:
        error_message = f"Error: {str(e)}"
        print(f"Error: {error_message}")
        logging.getLogger('general_errors').error(error_message)
        sys.exit(1)

    try:
        os.makedirs(args.screenshot_dir, exist_ok=True)
    except Exception as e:
        error_message = f"Error creating screenshot directory: {str(e)}"
        print(f"Error: {error_message}")
        logging.getLogger('general_errors').error(error_message)
        sys.exit(1)

    setup_logging(args.screenshot_dir)

    if not os.path.exists(args.domains):
        error_message = f"Domains file '{args.domains}' does not exist."
        print(f"Error: {error_message}")
        logging.getLogger('general_errors').error(error_message)
        sys.exit(1)

    try:
        with open(args.domains, "r") as file:
            domains = [line.strip() for line in file if line.strip()]
    except Exception as e:
        error_message = f"Error reading domains file: {str(e)}"
        print(f"Error: {error_message}")
        logging.getLogger('general_errors').error(error_message)
        sys.exit(1)

    if not domains:
        error_message = "No domains to process."
        print(f"Error: {error_message}")
        logging.getLogger('general_errors').error(error_message)
        sys.exit(1)

    # Remove duplicates from domains list
    domains = list(set(domains))

    session_file = f"{os.path.basename(args.domains)}_{os.path.basename(args.screenshot_dir)}.session"

    try:
        process_domains(domains, args.screenshot_dir, args.vpn_dir, args.max_requests, args.threads, args.timeout, webdriver_path, session_file, args.delay)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        error_message = f"An unexpected error occurred: {str(e)}"
        print(f"Error: {error_message}")
        logging.getLogger('general_errors').error(error_message)
        sys.exit(1)

if __name__ == "__main__":
    main()
