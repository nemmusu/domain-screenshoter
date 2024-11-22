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
    try:
        with open(log_file, "r") as f:
            for line in f:
                if target_error in line:
                    domain = line.split(":")[0].strip()
                    failed_domains.append(domain)
    except Exception:
        pass
    return failed_domains

def save_retry_session(retry_file, failed_domains, processed_domains, screenshots_done):
    retry_data = {
        "failed_domains": failed_domains,
        "processed_domains": processed_domains,
        "screenshots_done": screenshots_done
    }
    try:
        with open(retry_file, "w") as f:
            json.dump(retry_data, f)
    except Exception:
        pass

def load_retry_session(retry_file):
    if os.path.exists(retry_file):
        try:
            with open(retry_file, "r") as f:
                data = json.load(f)
                return data.get("failed_domains", []), data.get("processed_domains", 0), data.get("screenshots_done", 0)
        except Exception:
            return [], 0, 0
    return [], 0, 0

def retry_failed_domains(failed_domains, output_folder, vpn_dir, max_requests, threads, timeout, webdriver_path, delay, log_file):
    retry_file = f"retry_{os.path.basename(log_file).replace('.txt', '.session')}"
    retry_session, processed_domains, screenshots_done = load_retry_session(retry_file)
    if retry_session:
        print(f"Retry session found with {len(retry_session)} domains to process.")
        print(f"Processed {processed_domains}/{len(failed_domains)} domains, {screenshots_done} screenshots taken. Continue? (y/n)")
        try:
            choice = input().strip().lower()
        except EOFError:
            choice = 'n'
        if choice == "y":
            failed_domains = retry_session
        else:
            try:
                os.remove(retry_file)
            except Exception:
                pass
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
                except Exception:
                    logging.error(f"{domain}: Unexpected error during retry.")
        except KeyboardInterrupt:
            tqdm.write("\nInterrupted during retry. Saving retry session...")
            save_retry_session(retry_file, remaining_failed_domains, processed_domains, screenshots_done)
            print(f"Retry session saved as '{retry_file}'. You can resume it later.")
            sys.exit(0)
    progress_bar_domains.close()
    progress_bar_screenshots.close()
    if remaining_failed_domains:
        try:
            with open(log_file, "w") as log:
                for domain in remaining_failed_domains:
                    log.write(f"{domain}: timeout: Timed out receiving message from renderer\n")
        except Exception:
            pass
    else:
        try:
            if os.path.exists(log_file):
                os.remove(log_file)
        except Exception:
            pass
    if os.path.exists(retry_file):
        try:
            os.remove(retry_file)
        except Exception:
            pass
    print(f"Retry completed. {len(success_domains)} domains succeeded, {len(remaining_failed_domains)} still failed.")

def validate_session(domains, screenshot_dir, session):
    processed_domains = session.get("processed_domains", [])
    screenshots_done = session.get("screenshots_done", 0)
    actual_screenshots = len([f for f in os.listdir(screenshot_dir) if f.endswith(".png")])
    screenshots_done = actual_screenshots
    if len(processed_domains) > len(domains):
        processed_domains = processed_domains[:len(domains)]
    return processed_domains, screenshots_done

def setup_logging(output_folder):
    log_file = os.path.join(output_folder, "error_log.txt")
    logging.basicConfig(filename=log_file, level=logging.ERROR, format="%(message)s")

def get_webdriver_path(config_file="config.ini"):
    config = configparser.ConfigParser()
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Configuration file '{config_file}' not found.")
    config.read(config_file)
    if not config.has_section("settings"):
        raise ValueError("Missing 'settings' section in config.ini.")
    webdriver_path = config.get("settings", "webdriver_path", fallback=None)
    if not webdriver_path or not os.path.exists(webdriver_path):
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
        logging.error(f"VPN connection error: {str(e)}")
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
        logging.error(f"{domain}: WebDriver initialization failed.")
        return False
    try:
        url = f"http://{domain}"
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        screenshot_path = os.path.join(output_folder, f"{domain}.png")
        driver.save_screenshot(screenshot_path)
        return os.path.exists(screenshot_path)
    except (WebDriverException, TimeoutException):
        logging.error(f"{domain}: timeout: Timed out receiving message from renderer")
        return False
    except Exception:
        logging.error(f"{domain}: Unexpected error during screenshot.")
        return False
    finally:
        driver.quit()

def save_session(session_file, processed_domains, remaining_domains, screenshots_done):
    session_data = {
        "processed_domains": processed_domains,
        "remaining_domains": remaining_domains,
        "screenshots_done": screenshots_done,
    }
    try:
        with open(session_file, "w") as f:
            json.dump(session_data, f)
    except Exception:
        pass

def load_session(session_file):
    if os.path.exists(session_file):
        try:
            with open(session_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def process_domains(domains, output_folder, vpn_dir, max_requests, threads, timeout, webdriver_path, session_file, delay):
    vpn_process = None
    processed_domains = []
    screenshots_done = 0
    log_file = os.path.join(output_folder, "error_log.txt")
    session = load_session(session_file)
    if session:
        processed_domains, screenshots_done = validate_session(domains, output_folder, session)
        print(f"Session found for file '{os.path.basename(session_file)}' with {len(processed_domains)}/{len(domains)} domains processed and {screenshots_done} screenshots completed. Continue? (y/n)")
        try:
            choice = input().strip().lower()
        except EOFError:
            choice = 'n'
        if choice == "y":
            remaining_domains = [d for d in domains if d not in processed_domains]
            if len(processed_domains) == len(domains):
                failed_domains = parse_error_log(log_file)
                if failed_domains:
                    print(f"{len(failed_domains)} domains failed due to timeout errors. Retry? (y/n)")
                    try:
                        retry_choice = input().strip().lower()
                    except EOFError:
                        retry_choice = 'n'
                    if retry_choice == "y":
                        retry_failed_domains(failed_domains, output_folder, vpn_dir, max_requests, threads, timeout, webdriver_path, delay, log_file)
                return
        else:
            try:
                os.remove(session_file)
            except Exception:
                pass
            processed_domains, screenshots_done = [], 0
            remaining_domains = domains
    else:
        remaining_domains = domains
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
                    try:
                        vpn_process.terminate()
                        vpn_process.wait(timeout=5)
                    except Exception:
                        pass
                vpn_process = connect_vpn(vpn_dir)
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
                save_session(session_file, processed_domains, remaining_domains[i:], screenshots_done)
                if vpn_process:
                    try:
                        vpn_process.terminate()
                    except Exception:
                        pass
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
                            screenshots_done = reconcile_screenshots(output_folder, screenshots_done)
                            progress_bar_screenshots.n = screenshots_done
                            progress_bar_screenshots.refresh()
                    except Exception:
                        logging.error(f"{domain}: Unexpected error during processing.")
            except KeyboardInterrupt:
                tqdm.write("\nInterrupted. Saving session...")
                save_session(session_file, processed_domains, remaining_domains[i + completed_requests:], screenshots_done)
                if vpn_process:
                    try:
                        vpn_process.terminate()
                    except Exception:
                        pass
                print(f"Session saved as '{session_file}'. You can resume it later.")
                sys.exit(0)
    if vpn_process:
        try:
            vpn_process.terminate()
        except Exception:
            pass
    save_session(session_file, processed_domains, [], screenshots_done)
    progress_bar_domains.close()
    progress_bar_screenshots.close()
    progress_bar_requests.close()
    failed_domains = parse_error_log(log_file)
    if failed_domains:
        print(f"{len(failed_domains)} domains failed due to timeout errors. Retry? (y/n)")
        try:
            retry_choice = input().strip().lower()
        except EOFError:
            retry_choice = 'n'
        if retry_choice == "y":
            retry_failed_domains(failed_domains, output_folder, vpn_dir, max_requests, threads, timeout, webdriver_path, delay, log_file)

def reconcile_screenshots(output_folder, screenshots_done):
    actual_screenshots = len([f for f in os.listdir(output_folder) if f.endswith(".png")])
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
    try:
        if not os.path.exists(args.vpn_dir):
            print(f"Error: VPN directory '{args.vpn_dir}' does not exist.")
            sys.exit(1)
        ovpn_files = [f for f in os.listdir(args.vpn_dir) if f.endswith(".ovpn")]
        if not ovpn_files:
            print(f"Error: No VPN configuration files found in '{args.vpn_dir}'.")
            sys.exit(1)
    except Exception as e:
        print(f"Error accessing VPN directory: {str(e)}")
        sys.exit(1)
    try:
        webdriver_path = get_webdriver_path()
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)
    try:
        os.makedirs(args.screenshot_dir, exist_ok=True)
    except Exception as e:
        print(f"Error creating screenshot directory: {str(e)}")
        sys.exit(1)
    setup_logging(args.screenshot_dir)
    if not os.path.exists(args.domains):
        print(f"Error: Domains file '{args.domains}' does not exist.")
        sys.exit(1)
    try:
        with open(args.domains, "r") as file:
            domains = [line.strip() for line in file if line.strip()]
    except Exception as e:
        print(f"Error reading domains file: {str(e)}")
        sys.exit(1)
    if not domains:
        print("Error: No domains to process.")
        sys.exit(1)
    session_file = f"{os.path.basename(args.domains)}_{os.path.basename(args.screenshot_dir)}.session"
    try:
        process_domains(domains, args.screenshot_dir, args.vpn_dir, args.max_requests, args.threads, args.timeout, webdriver_path, session_file, args.delay)
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
