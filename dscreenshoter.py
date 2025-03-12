#!/usr/bin/env python3
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

def banner():
    print(r"""         _                                  _           _            
        | |                                | |         | |           
      __| |___  ___ _ __ ___  ___ _ __  ___| |__   ___ | |_ ___ _ __ 
     / _` / __|/ __| '__/ _ \/ _ \ '_ \/ __| '_ \ / _ \| __/ _ \ '__|
    | (_| \__ \ (__| | |  __/  __/ | | \__ \ | | | (_) | ||  __/ |   
     \__,_|___/\___|_|  \___|\___|_| |_|___/_| |_|\___/ \__\___|_|   
                                                                     
                                                                     """)

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

def ensure_session_dir():
    session_dir = "session"
    os.makedirs(session_dir, exist_ok=True)
    return session_dir

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

def get_nordvpn_ip():
    try:
        result = subprocess.run(["nordvpn", "status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("IP:"):
                return line.split("IP:")[1].strip()
    except Exception:
        pass
    return "???"

def wait_for_vpn_connection_nordvpn():
    time.sleep(5)
    return get_nordvpn_ip()

def connect_vpn_nordvpn():
    countries = ["Italy", "France", "Germany", "Spain", "United_States", "United_Kingdom", "Canada", "Brazil", "Sweden", "Australia"]
    random_country = random.choice(countries)
    try:
        subprocess.run(["nordvpn", "disconnect"], check=True)
        subprocess.run(["nordvpn", "connect", random_country], check=True)
        time.sleep(5)
        return random_country
    except subprocess.CalledProcessError as e:
        logging.getLogger('general_errors').error(f"NordVPN connection error: {str(e)}")
        return None

def disconnect_vpn_nordvpn():
    try:
        subprocess.run(["nordvpn", "disconnect"], check=True)
    except subprocess.CalledProcessError as e:
        logging.getLogger('general_errors').error(f"Failed to disconnect NordVPN: {str(e)}")

def connect_vpn_openvpn(ovpn_dir):
    try:
        ovpn_files = [f for f in os.listdir(ovpn_dir) if f.endswith(".ovpn")]
        if not ovpn_files:
            raise FileNotFoundError("No .ovpn files found.")
        chosen = random.choice(ovpn_files)
        path_ovpn = os.path.join(ovpn_dir, chosen)
        vpn_process = subprocess.Popen(["openvpn", "--config", path_ovpn], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return vpn_process, chosen
    except Exception as e:
        logging.getLogger('general_errors').error(f"OpenVPN connection error: {str(e)}")
        return None, None

def disconnect_vpn_openvpn(vpn_process):
    if vpn_process:
        try:
            vpn_process.terminate()
            vpn_process.wait(timeout=5)
        except Exception:
            logging.getLogger('general_errors').error("Failed to terminate OpenVPN process.")

def wait_for_vpn_connection_openvpn(timeout=30):
    time.sleep(5)
    return True

def take_screenshot(domain, output_folder, timeout, webdriver_path):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")
    options.set_capability("acceptInsecureCerts", True)
    
    try:
        service = Service(webdriver_path)
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        logging.getLogger('general_errors').error(f"{domain}: WebDriver initialization failed.")
        return False

    success = False
    try:
        for protocol in ["http://", "https://"]:
            try:
                driver.set_page_load_timeout(timeout)
                driver.get(protocol + domain)
                screenshot_path = os.path.join(output_folder, f"{domain}.png")
                driver.save_screenshot(screenshot_path)
                if os.path.exists(screenshot_path):
                    success = True
                    break 
            except TimeoutException:
                logging.getLogger('domain_errors').error(f"{domain}: timeout: Timed out receiving message from renderer")
            except WebDriverException:
                logging.getLogger('domain_errors').error(f"{domain}: Failed to load {protocol}{domain}")
            except Exception as e:
                logging.getLogger('domain_errors').error(f"{domain}: Unexpected error during screenshot: {e}")
    finally:
        driver.quit()
        
    return success


def retry_failed_domains(session_file, output_folder, max_requests, threads, timeout, webdriver_path, delay, use_nordvpn, ovpn_dir):
    retry_file = f"{os.path.basename(session_file)}.retry.session"
    while True:
        retry_session = load_retry_session(retry_file)
        if retry_session:
            remaining_domains = retry_session.get("remaining_domains", [])
            processed_domains = retry_session.get("processed_domains", [])
            screenshots_done = retry_session.get("screenshots_done", 0)
            failed_domains_set = set(retry_session.get("failed_domains", []))
            if not remaining_domains and failed_domains_set:
                remaining_domains = list(failed_domains_set)
                processed_domains = []
                screenshots_done = 0
                failed_domains_set = set()
                total_domains = len(remaining_domains)
                print(f"{total_domains} domains still failed. Retrying.")
            elif not remaining_domains and not failed_domains_set:
                print("All domains have been successfully processed after retry.")
                if os.path.exists(retry_file):
                    os.remove(retry_file)
                return False
            else:
                total_domains = len(remaining_domains) + len(processed_domains)
                print(f"Found a retry session with {len(remaining_domains)} domains to process.")
                print(f"Processed {len(processed_domains)}/{total_domains} domains, {screenshots_done} screenshots done.")
                while True:
                    try:
                        print("Continue? (type 'y' to continue, 'n' to start a new session):")
                        choice = input().strip().lower()
                        if choice == 'y':
                            break
                        elif choice == 'n':
                            os.remove(retry_file)
                            return False
                        else:
                            print("Invalid input. Type 'y' or 'n'.")
                    except KeyboardInterrupt:
                        print("\nOperation canceled by user.")
                        sys.exit(0)
        else:
            session = load_session(session_file)
            if not session or "failed_domains" not in session or not session["failed_domains"]:
                print("No failed domains to retry.")
                return False
            remaining_domains = list(set(session["failed_domains"]))
            processed_domains = []
            screenshots_done = 0
            failed_domains_set = set()
            total_domains = len(remaining_domains)
            print(f"{len(remaining_domains)} domains previously failed. Retrying with VPN rotation now.")
        progress_bar_domains = tqdm(total=total_domains, desc="Domains (retry) / total", position=0, unit="dom")
        progress_bar_screenshots = tqdm(total=total_domains, desc="Screenshots (retry) / total", position=1, unit="dom")
        progress_bar_requests = tqdm(total=max_requests, desc="Requests / total", position=2, unit="dom")
        progress_bar_domains.update(len(processed_domains))
        progress_bar_screenshots.update(screenshots_done)
        ip_counter = 0
        vpn_process = None
        with ThreadPoolExecutor(max_workers=threads) as executor:
            for i in range(0, len(remaining_domains), max_requests):
                connection_attempts = 0
                connected = False
                while not connected and connection_attempts < 5:
                    if use_nordvpn:
                        disconnect_vpn_nordvpn()
                        country = connect_vpn_nordvpn()
                        if not country:
                            connection_attempts += 1
                            continue
                        current_ip = wait_for_vpn_connection_nordvpn()
                        if current_ip and current_ip != "???":
                            connected = True
                            ip_counter += 1
                            tqdm.write(f"NordVPN connection #{ip_counter}: {country}, IP = {current_ip}")
                        else:
                            tqdm.write("NordVPN connection failed. Retrying...")
                            connection_attempts += 1
                    else:
                        if vpn_process:
                            disconnect_vpn_openvpn(vpn_process)
                        vpn_process, chosen_ovpn = connect_vpn_openvpn(ovpn_dir)
                        if not vpn_process:
                            connection_attempts += 1
                            continue
                        ok = wait_for_vpn_connection_openvpn()
                        if ok:
                            connected = True
                            ip_counter += 1
                            tqdm.write(f"OpenVPN connection #{ip_counter}: {chosen_ovpn}")
                        else:
                            tqdm.write("OpenVPN connection failed. Retrying...")
                            connection_attempts += 1
                if not connected:
                    tqdm.write("Unable to connect after 5 attempts. Saving state and exiting.")
                    save_retry_session(retry_file, processed_domains, remaining_domains[i:], screenshots_done, list(failed_domains_set))
                    if vpn_process:
                        disconnect_vpn_openvpn(vpn_process)
                    sys.exit(1)
                batch_domains = remaining_domains[i : i + max_requests]
                progress_bar_requests.reset()
                completed_requests = 0
                futures = {
                    executor.submit(take_screenshot, domain, output_folder, timeout, webdriver_path): domain
                    for domain in batch_domains
                }
                try:
                    for future in as_completed(futures):
                        domain = futures[future]
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
                    print("\nInterrupted by user. Saving retry state...")
                    save_retry_session(retry_file, processed_domains, remaining_domains[i + completed_requests:], screenshots_done, list(failed_domains_set))
                    print(f"Retry session saved to '{retry_file}'.")
                    if vpn_process:
                        disconnect_vpn_openvpn(vpn_process)
                    sys.exit(0)
                finally:
                    save_retry_session(retry_file, processed_domains, remaining_domains[i + completed_requests:], screenshots_done, list(failed_domains_set))
            if vpn_process:
                disconnect_vpn_openvpn(vpn_process)
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
            print(f"{len(failed_domains_set)} domains still failed after retry.")
            while True:
                try:
                    print("Retry again? (type 'y' to retry, 'n' to exit):")
                    retry_choice = input().strip().lower()
                    if retry_choice == 'y':
                        save_retry_session(retry_file, [], list(failed_domains_set), 0, [])
                        break
                    elif retry_choice == 'n':
                        print("Exiting retry attempts.")
                        if os.path.exists(retry_file):
                            os.remove(retry_file)
                        return False
                    else:
                        print("Invalid input. Type 'y' or 'n'.")
                except KeyboardInterrupt:
                    print("\nOperation canceled by user.")
                    sys.exit(0)
        else:
            print("All domains were successfully processed after retry.")
            if os.path.exists(retry_file):
                os.remove(retry_file)
            return False

def process_domains(domains, output_folder, max_requests, threads, timeout, webdriver_path, session_file, delay, use_nordvpn, ovpn_dir):
    session = load_session(session_file)
    if session:
        processed_domains = session.get("processed_domains", [])
        screenshots_done = session.get("screenshots_done", 0)
        failed_domains = set(session.get("failed_domains", []))
        print(f"Session found: {len(processed_domains)}/{len(domains)} domains already processed, {screenshots_done} screenshots done.")
        while True:
            try:
                print("Continue? (type 'y' to continue, 'n' to start a new session):")
                choice = input().strip().lower()
                if choice == 'y':
                    break
                elif choice == 'n':
                    try:
                        os.remove(os.path.join('session', session_file))
                    except:
                        pass
                    processed_domains, screenshots_done, failed_domains = [], 0, set()
                    domains = list(set(domains))
                    break
                else:
                    print("Invalid input. Type 'y' or 'n'.")
            except KeyboardInterrupt:
                print("\nOperation canceled by user.")
                sys.exit(0)
    else:
        print("No session found. Starting a new session.")
        processed_domains, screenshots_done, failed_domains = [], 0, set()
        domains = list(set(domains))

    total_domains = len(domains)
    remaining_domains = [d for d in domains if d not in processed_domains and d not in failed_domains]
    if remaining_domains:
        pbar_domains = tqdm(total=total_domains, desc="Domains processed / total", position=0, unit="dom")
        pbar_screenshots = tqdm(total=total_domains, desc="Screenshots taken / total", position=1, unit="dom")
        pbar_requests = tqdm(total=max_requests, desc="Requests / total", position=2, unit="dom")
        pbar_domains.update(len(processed_domains))
        pbar_screenshots.update(screenshots_done)
        ip_counter = 0
        vpn_process = None
        with ThreadPoolExecutor(max_workers=threads) as executor:
            for i in range(0, len(remaining_domains), max_requests):
                connection_attempts = 0
                connected = False
                while not connected and connection_attempts < 5:
                    if use_nordvpn:
                        disconnect_vpn_nordvpn()
                        country = connect_vpn_nordvpn()
                        if not country:
                            connection_attempts += 1
                            continue
                        current_ip = wait_for_vpn_connection_nordvpn()
                        if current_ip and current_ip != "???":
                            connected = True
                            ip_counter += 1
                            tqdm.write(f"VPN #{ip_counter}: NordVPN {country}, IP: {current_ip}")
                        else:
                            tqdm.write("NordVPN connection failed. Retrying...")
                            connection_attempts += 1
                    else:
                        if vpn_process:
                            disconnect_vpn_openvpn(vpn_process)
                        vpn_process, chosen_ovpn = connect_vpn_openvpn(ovpn_dir)
                        if not vpn_process:
                            connection_attempts += 1
                            continue
                        ok = wait_for_vpn_connection_openvpn()
                        if ok:
                            connected = True
                            ip_counter += 1
                            tqdm.write(f"VPN #{ip_counter}: OpenVPN with {chosen_ovpn}")
                        else:
                            tqdm.write("OpenVPN connection failed. Retrying...")
                            connection_attempts += 1
                if not connected:
                    tqdm.write("Unable to connect after 5 attempts. Saving session and exiting.")
                    save_session(session_file, processed_domains, remaining_domains[i:], screenshots_done, failed_domains)
                    if vpn_process:
                        disconnect_vpn_openvpn(vpn_process)
                    sys.exit(1)
                batch_domains = remaining_domains[i : i + max_requests]
                pbar_requests.reset()
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
                            pbar_requests.update(1)
                            pbar_domains.update(1)
                            processed_domains.append(domain)
                            if success:
                                screenshots_done += 1
                                pbar_screenshots.update(1)
                            else:
                                failed_domains.add(domain)
                        except Exception:
                            logging.getLogger('domain_errors').error(f"{domain}: Unexpected error.")
                            failed_domains.add(domain)
                except KeyboardInterrupt:
                    interrupted = True
                finally:
                    save_session(session_file, processed_domains, remaining_domains[i + completed_requests:], screenshots_done, failed_domains)
                    if interrupted:
                        tqdm.write(f"\nOperation canceled by user, session saved as '{session_file}'.")
                        if vpn_process:
                            disconnect_vpn_openvpn(vpn_process)
                        sys.exit(0)
            if not use_nordvpn and vpn_process:
                disconnect_vpn_openvpn(vpn_process)
        save_session(session_file, processed_domains, [], screenshots_done, failed_domains)
        pbar_domains.close()
        pbar_screenshots.close()
        pbar_requests.close()
    else:
        print("All domains were already processed.")

    if failed_domains:
        print(f"{len(failed_domains)} domains failed.")
        while True:
            print("Do you want to retry? (type 'y' to retry, 'n' to skip):")
            retry_choice = input().strip().lower()
            if retry_choice == 'y':
                continue_retry = retry_failed_domains(session_file, output_folder, max_requests, threads, timeout, webdriver_path, delay, use_nordvpn, ovpn_dir)
                if not continue_retry:
                    break
                session = load_session(session_file)
                failed_domains = set(session.get("failed_domains", []))
                if failed_domains:
                    print(f"{len(failed_domains)} domains still failed after retry.")
                else:
                    print("All domains were successfully processed after retry.")
                    break
            elif retry_choice == 'n':
                print("Skipping retry.")
                break
            else:
                print("Invalid input. Type 'y' or 'n'.")
    else:
        print("No domains failed, everything is fine.")

def main():
    banner()
    parser = argparse.ArgumentParser(description="Screenshot tool with VPN rotation (NordVPN or OpenVPN).")
    parser.add_argument("-d", "--domains", required=True, help="File with the list of domains.")
    parser.add_argument("-s", "--screenshot-dir", required=True, help="Folder for saving screenshots.")
    parser.add_argument("-n", "--max-requests", type=int, required=True, help="Number of requests before changing VPN.")
    parser.add_argument("-t", "--threads", type=int, required=True, help="Thread pool size.")
    parser.add_argument("--timeout", type=int, required=True, help="Page load timeout.")
    parser.add_argument("-de", "--delay", type=int, default=0, help="Delay in seconds (not strictly used).")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ovpn-dir", help="Folder with .ovpn files for OpenVPN.")
    group.add_argument("--use-nordvpn", action="store_true", help="Use NordVPN instead of OpenVPN.")

    args = parser.parse_args()

    if args.ovpn_dir and not os.path.exists(args.ovpn_dir):
        print(f"Error: folder '{args.ovpn_dir}' does not exist.")
        sys.exit(1)
    if args.ovpn_dir:
        ovpn_files = [f for f in os.listdir(args.ovpn_dir) if f.endswith(".ovpn")]
        if not ovpn_files:
            print(f"No .ovpn files found in '{args.ovpn_dir}'.")
            sys.exit(1)

    try:
        os.makedirs(args.screenshot_dir, exist_ok=True)
    except Exception as e:
        print(f"Error: unable to create folder '{args.screenshot_dir}': {e}")
        sys.exit(1)

    setup_logging(args.screenshot_dir)

    if not os.path.exists(args.domains):
        print(f"Error: domains file '{args.domains}' does not exist.")
        sys.exit(1)
    try:
        with open(args.domains, "r") as f:
            domains = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error reading '{args.domains}': {e}")
        sys.exit(1)

    if not domains:
        print("No domains to process.")
        sys.exit(1)

    try:
        webdriver_path = get_webdriver_path()
    except Exception as e:
        print(f"Error getting webdriver path: {e}")
        sys.exit(1)

    session_file = f"{os.path.basename(args.domains)}_{os.path.basename(args.screenshot_dir)}.session"
    try:
        use_nord = args.use_nordvpn
        ovpn_dir = args.ovpn_dir if not use_nord else None
        process_domains(domains, args.screenshot_dir, args.max_requests, args.threads, args.timeout, webdriver_path, session_file, args.delay, use_nord, ovpn_dir)
    except KeyboardInterrupt:
        print("\nOperation canceled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
