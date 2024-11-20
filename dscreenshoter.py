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
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import logging
import json


def validate_session(domains, screenshot_dir, session):
    processed_domains = session["processed_domains"]
    screenshots_done = session["screenshots_done"]

    # Reconcile processed_domains with actual saved screenshots
    actual_screenshots = len([f for f in os.listdir(screenshot_dir) if f.endswith(".png")])
    if screenshots_done != actual_screenshots:
        tqdm.write(f"Adjusting screenshots count: {screenshots_done} -> {actual_screenshots}")
        screenshots_done = actual_screenshots

    # Ensure processed_domains count matches total domains
    if len(processed_domains) > len(domains):
        tqdm.write("Warning: Processed domains exceed total domains. Adjusting session data.")
        processed_domains = domains[:len(domains)]

    return processed_domains, screenshots_done


def setup_logging(output_folder):
    log_file = os.path.join(output_folder, "error_log.txt")
    logging.basicConfig(filename=log_file, level=logging.ERROR, format="%(message)s")


def get_webdriver_path(config_file="config.ini"):
    config = configparser.ConfigParser()
    config.read(config_file)
    webdriver_path = config.get("settings", "webdriver_path", fallback=None)
    if not webdriver_path or not os.path.exists(webdriver_path):
        raise ValueError("WebDriver path not found in config.ini.")
    return webdriver_path


def connect_vpn(vpn_dir):
    ovpn_file = random.choice(os.listdir(vpn_dir))
    ovpn_path = os.path.join(vpn_dir, ovpn_file)
    vpn_process = subprocess.Popen(
        ["sudo", "openvpn", "--config", ovpn_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return vpn_process


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
        if current_ip != initial_ip:
            return current_ip
        time.sleep(2)
    return None


def take_screenshot(domain, output_folder, timeout, webdriver_path):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(webdriver_path)
    driver = webdriver.Chrome(service=service, options=options)

    try:
        url = f"http://{domain}"
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        screenshot_path = os.path.join(output_folder, f"{domain}.png")
        driver.save_screenshot(screenshot_path)
        return True
    except (WebDriverException, TimeoutException) as e:
        error_message = str(e).splitlines()[0]
        logging.error(f"{domain}: {error_message}")
        return False
    finally:
        driver.quit()


def save_session(session_file, processed_domains, remaining_domains, screenshots_done):
    session_data = {
        "processed_domains": processed_domains,
        "remaining_domains": remaining_domains,
        "screenshots_done": screenshots_done,
    }
    with open(session_file, "w") as f:
        json.dump(session_data, f)


def load_session(session_file):
    if os.path.exists(session_file):
        with open(session_file, "r") as f:
            return json.load(f)
    return None


def process_domains(domains, output_folder, vpn_dir, max_requests, threads, timeout, webdriver_path, session_file, delay):
    vpn_process = None
    processed_domains = []
    remaining_domains = domains
    screenshots_done = 0

    session = load_session(session_file)
    if session:
        processed_domains, screenshots_done = validate_session(domains, output_folder, session)
        print(
            f"Session found for file '{os.path.basename(session_file)}' with {len(processed_domains)}/{len(domains)} domains processed and {screenshots_done} screenshots completed. Continue? (y/n)"
        )
        try:
            choice = input().strip().lower()
            if choice == "y":
                remaining_domains = [d for d in domains if d not in processed_domains]
                if len(processed_domains) == len(domains):  # If all domains are processed
                    print("Session already completed. Nothing to process.")
                    return  # Exit gracefully
            else:
                os.remove(session_file)
                processed_domains, remaining_domains, screenshots_done = [], domains, 0
        except KeyboardInterrupt:
            print("\nInterrupted during session load. Exiting.")
            sys.exit(0)
    else:
        processed_domains, remaining_domains, screenshots_done = [], domains, 0

    progress_bar_domains = tqdm(total=len(domains), desc="Domains processed / total", position=0)
    progress_bar_screenshots = tqdm(total=len(domains), desc="Screenshots taken / total", position=1)
    progress_bar_requests = tqdm(total=max_requests, desc="Requests made / total", position=2)

    progress_bar_domains.update(len(processed_domains))
    progress_bar_screenshots.update(screenshots_done)

    if len(processed_domains) == len(domains):
        progress_bar_domains.close()
        progress_bar_screenshots.close()
        progress_bar_requests.close()
        print("All domains have already been processed. Exiting.")
        return

    ip_counter = 0
    with ThreadPoolExecutor(max_workers=threads) as executor:
        for i in range(0, len(remaining_domains), max_requests):
            connection_attempts = 0
            connected = False
            while not connected and connection_attempts < 5:
                if vpn_process:
                    vpn_process.terminate()
                    time.sleep(delay)  # Wait before reconnecting to a new VPN

                vpn_process = connect_vpn(vpn_dir)
                current_ip = wait_for_vpn_connection()
                if current_ip and current_ip != "IP unavailable":
                    connected = True
                    ip_counter += 1
                    tqdm.write(f"Connected to IP #{ip_counter}: {current_ip}")
                else:
                    tqdm.write("VPN connection failed. Retrying...")
                    connection_attempts += 1

            if not connected:
                tqdm.write("Failed to connect to any VPN after 5 attempts. Saving session and exiting...")
                save_session(session_file, processed_domains, remaining_domains[i:], screenshots_done)
                if vpn_process:
                    vpn_process.terminate()
                sys.exit(1)

            batch_domains = remaining_domains[i : i + max_requests]
            progress_bar_requests.reset()

            futures = {
                executor.submit(take_screenshot, domain, output_folder, timeout, webdriver_path): domain
                for domain in batch_domains
            }

            completed_requests = 0
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
                    except Exception as e:
                        logging.error(f"{domain}: {str(e)}")
            except KeyboardInterrupt:
                tqdm.write("\nInterrupted. Saving session...")
                save_session(session_file, processed_domains, remaining_domains[i + completed_requests:], screenshots_done)
                if vpn_process:
                    vpn_process.terminate()
                sys.exit(0)

            if completed_requests < len(batch_domains):
                tqdm.write("Not all requests completed for this batch. Retrying...")
                save_session(session_file, processed_domains, remaining_domains[i + completed_requests:], screenshots_done)
                continue

    if vpn_process:
        vpn_process.terminate()

    save_session(session_file, processed_domains, [], screenshots_done)
    progress_bar_domains.close()
    progress_bar_screenshots.close()
    progress_bar_requests.close()


def main():
    parser = argparse.ArgumentParser(description="Domain screenshot tool with VPN.")
    parser.add_argument("--vpn-dir", required=True, help="Folder with VPN configuration files.")
    parser.add_argument("-d", "--domains", required=True, help="File with the list of domains to process.")
    parser.add_argument("-s", "--screenshot-dir", required=True, help="Folder to save screenshots.")
    parser.add_argument("-n", "--max-requests", type=int, required=True, help="Max requests before changing VPN.")
    parser.add_argument("-t", "--threads", type=int, required=True, help="Number of threads to use.")
    parser.add_argument("-to", "--timeout", type=int, required=True, help="Page load timeout.")
    parser.add_argument("-de", "--delay", type=int, default=0, help="Delay in seconds before connecting to a new VPN.")
    args = parser.parse_args()

    webdriver_path = get_webdriver_path()
    os.makedirs(args.screenshot_dir, exist_ok=True)
    setup_logging(args.screenshot_dir)

    with open(args.domains, "r") as file:
        domains = [line.strip() for line in file if line.strip()]

    session_file = f"{os.path.basename(args.domains)}_{os.path.basename(args.screenshot_dir)}.session"
    process_domains(domains, args.screenshot_dir, args.vpn_dir, args.max_requests, args.threads, args.timeout, webdriver_path, session_file, args.delay)


if __name__ == "__main__":
    main()
