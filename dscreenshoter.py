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
from threading import Lock
import subprocess
import logging
import json


def parse_error_log(log_file, target_error="timeout: Timed out receiving message from renderer"):
    if not os.path.exists(log_file):
        return []
    
    failed_domains = []
    with open(log_file, "r") as f:
        for line in f:
            if target_error in line:
                domain = line.split(":")[0].strip()
                failed_domains.append(domain)
    return failed_domains

def save_retry_session(retry_file, failed_domains, processed_domains, screenshots_done):
    retry_data = {
        "failed_domains": failed_domains,
        "processed_domains": processed_domains,
        "screenshots_done": screenshots_done
    }
    with open(retry_file, "w") as f:
        json.dump(retry_data, f)

def load_retry_session(retry_file):
    if os.path.exists(retry_file):
        with open(retry_file, "r") as f:
            data = json.load(f)
            return data.get("failed_domains", []), data.get("processed_domains", 0), data.get("screenshots_done", 0)
    return None, 0, 0

def retry_failed_domains(failed_domains, output_folder, vpn_dir, max_requests, threads, timeout, webdriver_path, delay, log_file):
    retry_file = f"retry_{os.path.basename(log_file).replace('.txt', '.session')}"
    retry_session, processed_domains, screenshots_done = load_retry_session(retry_file)
    
    if retry_session:
        print(f"Retry session found with {len(retry_session)} domains to process.")
        print(f"Processed {processed_domains}/{len(failed_domains)} domains, {screenshots_done} screenshots taken. Continue? (y/n)")
        choice = input().strip().lower()
        if choice == "y":
            failed_domains = retry_session
        else:
            os.remove(retry_file)
            processed_domains, screenshots_done = 0, 0

    if not failed_domains:
        return

    print(f"{len(failed_domains)} domains failed due to timeout errors. Retrying with IP rotation.")

    success_domains = []
    remaining_failed_domains = failed_domains.copy()

    progress_bar_domains = tqdm(total=len(failed_domains), desc="Retrying domains / total", position=0)
    progress_bar_screenshots = tqdm(total=len(failed_domains), desc="Screenshots taken / total", position=1)

    progress_bar_domains.update(processed_domains)
    progress_bar_screenshots.update(screenshots_done)

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {
            executor.submit(take_screenshot, domain, output_folder, timeout, webdriver_path): domain
            for domain in failed_domains
        }

        try:
            for future in as_completed(futures):
                domain = futures[future]
                try:
                    success = future.result()
                    processed_domains += 1
                    progress_bar_domains.update(1)
                    if success:
                        screenshots_done += 1
                        progress_bar_screenshots.update(1)
                        success_domains.append(domain)
                        remaining_failed_domains.remove(domain)
                except Exception as e:
                    logging.error(f"{domain}: {str(e)}")
        except KeyboardInterrupt:
            tqdm.write("\nInterrupted during retry. Saving retry session...")
            save_retry_session(retry_file, remaining_failed_domains, processed_domains, screenshots_done)
            print(f"Retry session saved as '{retry_file}'. You can resume it later.")
            sys.exit(0)

    progress_bar_domains.close()
    progress_bar_screenshots.close()

    if remaining_failed_domains:
        with open(log_file, "w") as log:
            for domain in remaining_failed_domains:
                log.write(f"{domain}: timeout: Timed out receiving message from renderer\n")
    else:
        if os.path.exists(log_file):
            os.remove(log_file)

    if os.path.exists(retry_file):
        os.remove(retry_file)

    print(f"Retry completed. {len(success_domains)} domains succeeded, {len(remaining_failed_domains)} still failed.")



def validate_session(domains, screenshot_dir, session):
    processed_domains = session["processed_domains"]
    screenshots_done = session["screenshots_done"]

    # Reconcile processed_domains with actual saved screenshots
    actual_screenshots = len([f for f in os.listdir(screenshot_dir) if f.endswith(".png")])
    if screenshots_done != actual_screenshots:
        #tqdm.write(f"Adjusting screenshots count: {screenshots_done} -> {actual_screenshots}")
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
        driver.save_screenshot(screenshot_path)  # Save the screenshot
        return os.path.exists(screenshot_path)  # Return True if the screenshot is saved successfully
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

    log_file = os.path.join(output_folder, "error_log.txt")  # Define the log file path

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
                    failed_domains = parse_error_log(log_file)
                    if failed_domains:
                        print(f"{len(failed_domains)} domains failed due to timeout errors. Retry? (y/n)")
                        retry_choice = input().strip().lower()
                        if retry_choice == "y":
                            retry_failed_domains(
                                failed_domains,
                                output_folder,
                                vpn_dir,
                                max_requests,
                                threads,
                                timeout,
                                webdriver_path,
                                delay,
                                log_file  # Pass the log file explicitly
                            )
                    return
            else:
                os.remove(session_file)  # Delete the session file if user chooses not to resume
                processed_domains, remaining_domains, screenshots_done = [], domains, 0
        except KeyboardInterrupt:
            print("\nInterrupted during session load. Exiting.")
            sys.exit(0)

    progress_bar_domains = tqdm(total=len(domains), desc="Domains processed / total", position=0)
    progress_bar_screenshots = tqdm(total=len(domains), desc="Screenshots taken / total", position=1)
    progress_bar_requests = tqdm(total=max_requests, desc="Requests made / total", position=2)

    progress_bar_domains.update(len(processed_domains))
    progress_bar_screenshots.update(screenshots_done)

    ip_counter = 0
    with ThreadPoolExecutor(max_workers=threads) as executor:
        for i in range(0, len(remaining_domains), max_requests):
            connection_attempts = 0
            connected = False
            while not connected and connection_attempts < 5:
                if vpn_process:
                    vpn_process.terminate()
                    time.sleep(delay)

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
                        success = future.result()  # True if screenshot is saved successfully
                        completed_requests += 1
                        progress_bar_requests.update(1)  # Update requests progress
                        progress_bar_domains.update(1)  # Update domains processed progress
                        processed_domains.append(domain)
                        if success:
                            # Reconcile screenshots count after saving the screenshot
                            screenshots_done = reconcile_screenshots(output_folder, screenshots_done)
                            progress_bar_screenshots.n = screenshots_done  # Update tqdm count
                            progress_bar_screenshots.refresh()  # Refresh the progress bar display
                    except Exception as e:
                        logging.error(f"{domain}: {str(e)}")
            except KeyboardInterrupt:
                tqdm.write("\nInterrupted. Saving session...")
                save_session(session_file, processed_domains, remaining_domains[i + completed_requests:], screenshots_done)
                if vpn_process:
                    vpn_process.terminate()
                print(f"Session saved as '{session_file}'. You can resume it later.")
                sys.exit(0)

    if vpn_process:
        vpn_process.terminate()

    save_session(session_file, processed_domains, [], screenshots_done)
    progress_bar_domains.close()
    progress_bar_screenshots.close()
    progress_bar_requests.close()

    failed_domains = parse_error_log(log_file)
    if failed_domains:
        print(f"{len(failed_domains)} domains failed due to timeout errors. Retry? (y/n)")
        retry_choice = input().strip().lower()
        if retry_choice == "y":
            retry_failed_domains(failed_domains, output_folder, vpn_dir, max_requests, threads, timeout, webdriver_path, delay, log_file)


def reconcile_screenshots(output_folder, screenshots_done):
    actual_screenshots = len([f for f in os.listdir(output_folder) if f.endswith(".png")])
    if screenshots_done != actual_screenshots:
        pass
        #tqdm.write(f"Reconciliation: Adjusting screenshots count: {screenshots_done} -> {actual_screenshots}")
    return actual_screenshots



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