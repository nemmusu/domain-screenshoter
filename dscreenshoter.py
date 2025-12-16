import os
import re
import sys
import time
import random
import argparse
import ipaddress
import configparser
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from bs4 import BeautifulSoup
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import subprocess
import logging
import json
from generate_report import generate_report

def banner():
    print(r"""         _                                  _           _            
        | |                                | |         | |           
      __| |___  ___ _ __ ___  ___ _ __  ___| |__   ___ | |_ ___ _ __ 
     / _` / __|/ __| '__/ _ \/ _ \ '_ \/ __| '_ \ / _ \| __/ _ \ '__|
    | (_| \__ \ (__| | |  __/  __/ | | \__ \ | | | (_) | ||  __/ |   
     \__,_|___/\___|_|  \___|\___|_| |_|___/_| |_|\___/ \__\___|_|      
                                                                     """)

def ensure_session_dir():
    session_dir = "session"
    os.makedirs(session_dir, exist_ok=True)
    return session_dir

def save_session(session_file, processed_domains, remaining_domains, screenshots_done, failed_domains, successful_domains_order=None, domain_urls=None, domain_titles=None, domain_status_codes=None, domain_body_excerpts=None):
    session_dir = ensure_session_dir()
    session_path = os.path.join(session_dir, session_file)
    session_data = {
        "processed_domains": processed_domains,
        "remaining_domains": remaining_domains,
        "screenshots_done": screenshots_done,
        "failed_domains": list(failed_domains),
        "successful_domains_order": successful_domains_order or [],
        "domain_urls": domain_urls or {},
        "domain_titles": domain_titles or {},
        "domain_status_codes": domain_status_codes or {},
        "domain_body_excerpts": domain_body_excerpts or {},
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

def get_current_ip():
    try:
        response = requests.get("https://ifconfig.me", timeout=10)
        return response.text.strip()
    except requests.RequestException:
        return "IP unavailable"

def wait_for_vpn_connection(old_ip=None, timeout=30):
    start_time = time.time()
    initial_ip = old_ip if old_ip else get_current_ip()
    while time.time() - start_time < timeout:
        current_ip = get_current_ip()
        if current_ip != initial_ip and current_ip != "IP unavailable":
            return current_ip
        time.sleep(2)
    return None

def connect_openvpn(vpn_dir):
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

def disconnect_openvpn(vpn_process):
    if vpn_process:
        try:
            vpn_process.terminate()
            vpn_process.wait(timeout=5)
        except Exception:
            logging.getLogger('general_errors').error("Failed to terminate OpenVPN process.")

def connect_nordvpn():
    try:
        subprocess.run(["nordvpn", "disconnect"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        cmd = ["nordvpn", "connect"]
        vpn_process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if vpn_process.returncode != 0:
            logging.getLogger('general_errors').error("NordVPN connection error.")
            return False
        return True
    except Exception as e:
        logging.getLogger('general_errors').error(f"NordVPN connection error: {str(e)}")
        return False

def expand_cidr(cidr):
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return []
    hosts = []
    for ip in net.hosts():
        hosts.append(str(ip))
    return hosts


def normalize_target(raw):
    raw = raw.strip()

    if raw.startswith(("http://", "https://")):
        return [raw]

    if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}$", raw):
        ips = expand_cidr(raw)
        urls = []
        for ip in ips:
            urls.append(f"https://{ip}")
            urls.append(f"http://{ip}")
        return urls

    if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", raw):
        return [
            f"https://{raw}",
            f"http://{raw}"
        ]

    return [
        f"https://{raw}",
        f"http://{raw}"
    ]


def safe_filename(value):
    return re.sub(r"[^a-zA-Z0-9._-]", "_", value)


def take_screenshot(domain, output_folder, timeout, webdriver_path, get_csv_data=False, accept_cookies=True):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--allow-insecure-localhost")

    try:
        service = Service(webdriver_path)
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_window_size(1920, 1080)

    except Exception as e:
        logging.getLogger('general_errors').error(f"{domain}: WebDriver initialization failed: {e}")
        return False, None

    try:
        urls = normalize_target(domain)
        urls_sorted = sorted(urls, key=lambda x: (0 if x.startswith('https://') else 1))

        for url in urls_sorted:
            try:
                driver.set_page_load_timeout(timeout)
                driver.get(url)
                
                if get_csv_data:
                    try:
                        driver.execute_script("return document.readyState === 'complete'")
                        time.sleep(0.5)
                    except:
                        time.sleep(0.5)
                else:
                    time.sleep(0.3)
                
                # Automatically accept cookie consent banners if enabled
                if accept_cookies:
                    try:
                        from selenium.webdriver.common.by import By
                        from selenium.webdriver.support.ui import WebDriverWait
                        from selenium.webdriver.support import expected_conditions as EC
                        
                        # High priority keywords: "accept all" variants (multilingual)
                        accept_keywords_priority = [
                            'accetta tutto', 'accetta tutti', 'accetto tutto', 'accetto tutti',
                            'sono d\'accordo', 'sono daccordo', 'accettare tutto',
                            'accept all', 'accept all cookies', 'i agree', 'i accept',
                            'accept cookies', 'agree to all', 'allow all',
                            'tout accepter', 'j\'accepte', 'j\'accepte tout', 'accepter tout',
                            'jaccepte', 'aceptar todo', 'acepto todo', 'aceptar todas',
                            'acepto todas', 'estoy de acuerdo', 'alle akzeptieren',
                            'alle annehmen', 'ich stimme zu', 'akzeptieren', 'annehmen',
                            'aceitar tudo', 'aceito tudo', 'concordo', 'aceitar todos',
                            'alles accepteren', 'ik ga akkoord', 'akkoord',
                            'zaakceptuj wszystko', 'akceptuję wszystko', 'zgadzam się',
                            'принять все', 'согласен', 'принимаю все',
                            'zenbu kyoka', 'kyoka suru', 'tongyi quanbu', 'jieshou quanbu',
                        ]
                        
                        # General accept keywords (multilingual)
                        accept_keywords = [
                            'accetta', 'accetto', 'accettare', 'consenti', 'consento',
                            'ok', 'va bene', 'conferma', 'accept', 'consent', 'agree',
                            'allow', 'confirm', 'yes', 'proceed', 'continue',
                            'accepter', 'consentir', 'd\'accord', 'daccord', 'oui',
                            'aceptar', 'acepto', 'consentir', 'consiento', 'de acuerdo',
                            'akzeptieren', 'annehmen', 'zustimmen', 'einverstanden',
                            'aceitar', 'aceito', 'concordar', 'consentir',
                            'accepteren', 'akkoord', 'toestemmen',
                            'akceptować', 'zgadzać się', 'zaakceptować',
                            'принять', 'согласиться', 'принимаю',
                            'kyoka', 'shoudaku', 'tongyi', 'jieshou',
                        ]
                        
                        # Keywords to avoid (open settings/menus)
                        reject_keywords = [
                            'personalizza', 'customize', 'settings', 'impostazioni',
                            'preferenze', 'preferences', 'options', 'opzioni',
                            'configura', 'configure', 'gestisci', 'manage',
                            'dettagli', 'details', 'more', 'più', 'more options',
                            'personaliser', 'personnaliser', 'paramètres',
                            'personalizar', 'configurar', 'preferencias',
                            'anpassen', 'einstellungen', 'konfigurieren',
                            'personalizar', 'configurar', 'preferências',
                        ]
                        
                        # Build dynamic XPath selectors for high priority keywords
                        cookie_selectors_priority = []
                        for keyword in accept_keywords_priority:
                            keyword_lower = keyword.lower()
                            cookie_selectors_priority.append(
                                f"//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ', 'abcdefghijklmnopqrstuvwxyzaaaaaaaaceeeeiiiidnoooooouuuuybsaaaaaaaceeeeiiiidnoooooouuuuyby'), '{keyword_lower}')]"
                            )
                        
                        # Build dynamic XPath selectors for general keywords (limit reject conditions to avoid overly long XPath)
                        cookie_selectors = []
                        for keyword in accept_keywords:
                            keyword_lower = keyword.lower()
                            reject_conditions = ' and '.join([f"not(contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ', 'abcdefghijklmnopqrstuvwxyzaaaaaaaaceeeeiiiidnoooooouuuuybsaaaaaaaceeeeiiiidnoooooouuuuyby'), '{rk}'))" for rk in reject_keywords[:3]])
                            cookie_selectors.append(
                                f"//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ', 'abcdefghijklmnopqrstuvwxyzaaaaaaaaceeeeiiiidnoooooouuuuybsaaaaaaaceeeeiiiidnoooooouuuuyby'), '{keyword_lower}') and {reject_conditions}]"
                            )
                        
                        # Add common CSS selectors
                        cookie_selectors.extend([
                            "button[id*='accept-all']", "button[id*='AcceptAll']", "button[id*='acceptAll']",
                            "button[class*='accept-all']", "button[class*='AcceptAll']",
                            "#accept-all", "#acceptAll", ".accept-all",
                            "button[id*='consent']", "button[id*='Consent']",
                            "button[class*='consent']", "button[class*='Consent']",
                            "#consent", ".consent", ".cookie-consent",
                            "button[id*='accept']", "button[id*='Accept']",
                            "button[class*='accept']", "button[class*='Accept']",
                            "#cookie-accept", "#accept-cookies", "#cookieAccept",
                            ".cookie-accept", ".accept-cookies",
                        ])
                        
                        cookie_clicked = False
                        
                        # Try high priority selectors first
                        for selector in cookie_selectors_priority:
                            try:
                                elements = driver.find_elements(By.XPATH, selector)
                                for element in elements:
                                    if element.is_displayed() and element.is_enabled():
                                        element.click()
                                        cookie_clicked = True
                                        time.sleep(0.2)
                                        break
                                if cookie_clicked:
                                    break
                            except:
                                continue
                        
                        # Try other selectors if high priority didn't work
                        if not cookie_clicked:
                            for selector in cookie_selectors:
                                try:
                                    if selector.startswith("//"):
                                        elements = driver.find_elements(By.XPATH, selector)
                                    else:
                                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                                    
                                    for element in elements:
                                        if element.is_displayed() and element.is_enabled():
                                            text = (element.text or "").lower()
                                            if any(reject_word in text for reject_word in reject_keywords):
                                                continue
                                            element.click()
                                            cookie_clicked = True
                                            time.sleep(0.2)
                                            break
                                    
                                    if cookie_clicked:
                                        break
                                except:
                                    continue
                        
                        # JavaScript fallback for hidden elements
                        if not cookie_clicked:
                            try:
                                driver.execute_script("""
                                    var buttons = document.querySelectorAll('button, a, [role="button"]');
                                    var priorityButtons = [];
                                    var otherButtons = [];
                                    
                                    var priorityKeywords = ['accetta tutto', 'accetta tutti', 'accetto tutto', 'accetto tutti',
                                        'sono d\\'accordo', 'sono daccordo', 'accept all', 'accept all cookies',
                                        'i agree', 'i accept', 'tout accepter', 'j\\'accepte', 'jaccepte',
                                        'aceptar todo', 'acepto todo', 'alle akzeptieren', 'aceitar tudo',
                                        'alles accepteren', 'ik ga akkoord', 'zaakceptuj wszystko'];
                                    
                                    var acceptKeywords = ['accetta', 'accetto', 'accettare', 'consenti', 'consento',
                                        'accept', 'consent', 'agree', 'allow', 'ok', 'confirm', 'yes',
                                        'accepter', 'consentir', 'd\\'accord', 'aceptar', 'acepto',
                                        'akzeptieren', 'annehmen', 'aceitar', 'aceito', 'accepteren',
                                        'akkoord', 'akceptować', 'consentir', 'consiento'];
                                    
                                    var rejectKeywords = ['personalizza', 'customize', 'settings', 'impostazioni',
                                        'preferenze', 'preferences', 'options', 'opzioni', 'configura',
                                        'configure', 'gestisci', 'manage', 'dettagli', 'details', 'more',
                                        'più', 'more options', 'personaliser', 'paramètres', 'personalizar',
                                        'configurar', 'preferencias', 'anpassen', 'einstellungen'];
                                    
                                    for (var i = 0; i < buttons.length; i++) {
                                        var text = (buttons[i].textContent || buttons[i].innerText || '').toLowerCase();
                                        var id = (buttons[i].id || '').toLowerCase();
                                        var className = (buttons[i].className || '').toLowerCase();
                                        
                                        var shouldReject = false;
                                        for (var j = 0; j < rejectKeywords.length; j++) {
                                            if (text.includes(rejectKeywords[j])) {
                                                shouldReject = true;
                                                break;
                                            }
                                        }
                                        if (shouldReject) continue;
                                        
                                        var isVisible = buttons[i].offsetParent !== null || buttons[i].style.display !== 'none';
                                        
                                        var isPriority = false;
                                        for (var j = 0; j < priorityKeywords.length; j++) {
                                            if (text.includes(priorityKeywords[j])) {
                                                isPriority = true;
                                                break;
                                            }
                                        }
                                        
                                        if (isPriority && isVisible) {
                                            priorityButtons.push(buttons[i]);
                                        } else {
                                            var isAccept = false;
                                            for (var j = 0; j < acceptKeywords.length; j++) {
                                                if (text.includes(acceptKeywords[j]) || 
                                                    id.includes(acceptKeywords[j]) || 
                                                    className.includes(acceptKeywords[j])) {
                                                    isAccept = true;
                                                    break;
                                                }
                                            }
                                            if (isAccept && isVisible) {
                                                otherButtons.push(buttons[i]);
                                            }
                                        }
                                    }
                                    
                                    if (priorityButtons.length > 0) {
                                        priorityButtons[0].click();
                                        return true;
                                    }
                                    if (otherButtons.length > 0) {
                                        otherButtons[0].click();
                                        return true;
                                    }
                                    return false;
                                """)
                            except:
                                pass
                    except:
                        pass

                total_width = driver.execute_script("return document.body.scrollWidth")
                total_height = driver.execute_script("return document.body.scrollHeight")
                
                max_width = 8000
                max_height = 50000
                total_width = min(total_width, max_width)
                total_height = min(total_height, max_height)
                
                driver.set_window_size(total_width, total_height)
                time.sleep(0.2)

                parsed = urlparse(url)
                host = parsed.netloc if parsed.netloc else parsed.path
                filename = safe_filename(host) + ".png"
                screenshots_folder = os.path.join(output_folder, "screenshots")
                os.makedirs(screenshots_folder, exist_ok=True)
                screenshot_path = os.path.join(screenshots_folder, filename)
                existed_before = os.path.exists(screenshot_path)

                if not existed_before:
                    driver.save_screenshot(screenshot_path)
                    if not (os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 5000):
                        continue

                try:
                    page_title = driver.title
                except:
                    page_title = ""
                
                if get_csv_data:
                    status_code = 200
                    try:
                        status_code = int(driver.execute_script("""
                            try {
                                var entries = performance.getEntriesByType('navigation');
                                if (entries && entries.length > 0) {
                                    return entries[0].responseStatus || entries[0].status || 200;
                                }
                                return 200;
                            } catch(e) {
                                return 200;
                            }
                        """))
                    except:
                        status_code = 200
                    
                    body_excerpt = ""
                    try:
                        body_excerpt = driver.execute_script("""
                            try {
                                var text = document.body.innerText || document.body.textContent || '';
                                return text.trim().substring(0, 200).replace(/\\s+/g, ' ');
                            } catch(e) {
                                return '';
                            }
                        """)
                        if not body_excerpt:
                            body_excerpt = ""
                    except:
                        body_excerpt = ""
                else:
                    status_code = None
                    body_excerpt = ""
                
                return (not existed_before, url, page_title, status_code, body_excerpt)

            except Exception as e:
                logging.getLogger('domain_errors').error(f"{domain}: URL error {url} → {e}")
                continue

        return False, None, "", None, ""

    except Exception as e:
        logging.getLogger('domain_errors').error(f"{domain}: Unexpected error during screenshot: {e}")
        return False, None, "", None, ""

    finally:
        try:
            driver.quit()
        except:
            pass


def process_domains(domains, output_folder, vpn_dir, max_requests, threads, timeout, webdriver_path, session_file, delay, vpn_mode, get_csv_data=False, accept_cookies=True):

    # Create screenshots subdirectory
    screenshots_folder = os.path.join(output_folder, "screenshots")
    os.makedirs(screenshots_folder, exist_ok=True)

    vpn_process = None
    session = load_session(session_file)
    domain_titles = {}
    domain_status_codes = {}
    domain_body_excerpts = {}
    if session:
        processed_domains_raw = session.get("processed_domains", [])
        screenshots_done = session.get("screenshots_done", 0)
        failed_domains = set(session.get("failed_domains", []))
        successful_domains_order = session.get("successful_domains_order", [])
        domain_urls = session.get("domain_urls", {})
        domain_titles = session.get("domain_titles", {})
        domain_status_codes = session.get("domain_status_codes", {})
        domain_body_excerpts = session.get("domain_body_excerpts", {})
        
        def normalize_domain_for_session(d):
            """Normalize expanded URLs to original domains"""
            if d.startswith(("http://", "https://")):
                domain = d.replace("http://", "").replace("https://", "")
                if not re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", domain):
                    return domain
                else:
                    return d
            return d
        
        processed_domains = []
        for pd in processed_domains_raw:
            normalized = normalize_domain_for_session(pd)
            if normalized not in processed_domains:
                processed_domains.append(normalized)
        
        failed_domains_normalized = set()
        for fd in failed_domains:
            normalized = normalize_domain_for_session(fd)
            failed_domains_normalized.add(normalized)
        failed_domains = failed_domains_normalized

        print(f"Found session '{os.path.basename(session_file)}' with {len(processed_domains)}/{len(domains)} processed. Screenshots done: {screenshots_done}.")

        while True:
            try:
                print("Continue this session? (y/n):")
                choice = input().strip().lower()
                if choice == 'y':
                    break

                elif choice == 'n':
                    try:
                        os.remove(os.path.join("session", session_file))
                    except Exception:
                        logging.getLogger('general_errors').error(f"Cannot remove session file '{session_file}'.")

                    processed_domains, screenshots_done, failed_domains = [], 0, set()
                    successful_domains_order = []
                    domain_urls = {}
                    domain_titles = {}
                    domain_status_codes = {}
                    domain_body_excerpts = {}
                    domains = list(set(domains))
                    break

                else:
                    print("Invalid input. Enter 'y' or 'n'.")

            except KeyboardInterrupt:
                print("\nOperation canceled by user.")
                sys.exit(0)

    else:
        print(f"No session found for '{os.path.basename(session_file)}'. Starting a new one.")
        processed_domains, screenshots_done, failed_domains = [], 0, set()
        successful_domains_order = []
        domain_urls = {}
        domain_titles = {}
        domain_status_codes = {}
        domain_body_excerpts = {}
        domains = list(set(domains))

    domains_to_process = []
    
    for d in domains:
        if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?$", d):
            expanded = normalize_target(d)
            domains_to_process.extend(expanded)
        else:
            domains_to_process.append(d)

    total_domains = len(domains_to_process)
    remaining_domains = [d for d in domains_to_process if d not in processed_domains]
    
    if get_csv_data:
        for domain in processed_domains:
            if domain in domains_to_process and (domain not in domain_status_codes or domain not in domain_body_excerpts):
                remaining_domains.append(domain)



    if remaining_domains:

        progress_bar_domains = tqdm(total=total_domains, desc="Processed domains / total", position=0, unit="domain")
        progress_bar_screenshots = tqdm(total=total_domains, desc="Screenshots OK / total", position=1, unit="domain")
        progress_bar_requests = tqdm(total=max_requests if max_requests else 0, desc="Requests / batch", position=2, unit="req")

        progress_bar_domains.update(len(processed_domains))
        progress_bar_screenshots.update(screenshots_done)

        ip_counter = 0

        with ThreadPoolExecutor(max_workers=threads) as executor:

            for i in range(0, len(remaining_domains), max_requests if max_requests else len(remaining_domains)):

                if vpn_mode != "none":

                    connection_attempts = 0
                    connected = False

                    while not connected and connection_attempts < 5:

                        if vpn_process and vpn_mode == "openvpn":
                            disconnect_openvpn(vpn_process)
                            vpn_process = None

                        elif vpn_mode == "nordvpn":
                            subprocess.run(["nordvpn", "disconnect"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                        if vpn_mode == "openvpn":
                            vpn_process = connect_openvpn(vpn_dir)
                            if vpn_process is None:
                                connection_attempts += 1
                                continue

                            old_ip = get_current_ip()
                            current_ip = wait_for_vpn_connection(old_ip=old_ip)

                            if current_ip:
                                connected = True
                                ip_counter += 1
                                tqdm.write(f"Connected with IP #{ip_counter}: {current_ip}")
                            else:
                                tqdm.write("OpenVPN connection failed. Retrying...")
                                connection_attempts += 1

                        elif vpn_mode == "nordvpn":

                            old_ip = get_current_ip()
                            ok = connect_nordvpn()

                            if not ok:
                                connection_attempts += 1
                                continue

                            current_ip = wait_for_vpn_connection(old_ip=old_ip)

                            if current_ip:
                                connected = True
                                ip_counter += 1
                                tqdm.write(f"Connected with NordVPN, IP #{ip_counter}: {current_ip}")
                            else:
                                tqdm.write("NordVPN connection failed. Retrying...")
                                connection_attempts += 1

                        time.sleep(delay)

                    if not connected:
                        tqdm.write("Could not connect to VPN after 5 attempts. Saving session and exiting...")
                        save_session(session_file, processed_domains, remaining_domains[i:], screenshots_done, failed_domains, successful_domains_order, domain_urls, domain_titles, domain_status_codes, domain_body_excerpts)
                        sys.exit(1)



                batch_domains = remaining_domains[i : i + (max_requests if max_requests else len(remaining_domains))]

                progress_bar_requests.reset()
                completed_requests = 0
                interrupted = False

                futures = {
                    executor.submit(take_screenshot, domain, output_folder, timeout, webdriver_path, get_csv_data, accept_cookies): domain
                    for domain in batch_domains
                }


                try:
                    for future in as_completed(futures):

                        domain = futures[future]

                        try:
                            result = future.result()
                            if len(result) == 5:
                                success, working_url, page_title, status_code, body_excerpt = result
                            elif len(result) == 3:
                                success, working_url, page_title = result
                                status_code, body_excerpt = None, ""
                            else:
                                success, working_url = result
                                page_title, status_code, body_excerpt = "", None, ""

                            completed_requests += 1
                            progress_bar_requests.update(1)

                            processed_domains.append(domain)
                            progress_bar_domains.update(1)

                            if working_url:
                                if success or domain not in successful_domains_order:
                                    screenshots_done += 1
                                    progress_bar_screenshots.update(1)
                                failed_domains.discard(domain)
                                if domain not in successful_domains_order:
                                    successful_domains_order.append(domain)
                                domain_urls[domain] = working_url
                                if page_title:
                                    domain_titles[domain] = page_title
                                if get_csv_data:
                                    domain_status_codes[domain] = str(status_code) if status_code is not None else ""
                                    domain_body_excerpts[domain] = str(body_excerpt) if body_excerpt else ""
                            else:
                                failed_domains.add(domain)

                        except Exception:
                            logging.getLogger('domain_errors').error(f"{domain}: Unexpected error.")
                            failed_domains.add(domain)

                except KeyboardInterrupt:
                    interrupted = True

                finally:
                    save_session(session_file, processed_domains, remaining_domains[i + completed_requests:], screenshots_done, failed_domains, successful_domains_order, domain_urls, domain_titles, domain_status_codes, domain_body_excerpts)

                    if interrupted:
                        tqdm.write(f"\nOperation canceled by user. Session saved as '{session_file}'.")
                        if vpn_process and vpn_mode == "openvpn":
                            disconnect_openvpn(vpn_process)
                        elif vpn_mode == "nordvpn":
                            subprocess.run(["nordvpn", "disconnect"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        sys.exit(0)



                if vpn_mode == "openvpn" and vpn_process:
                    disconnect_openvpn(vpn_process)
                    vpn_process = None

                elif vpn_mode == "nordvpn":
                    subprocess.run(["nordvpn", "disconnect"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)



        if vpn_mode == "openvpn" and vpn_process:
            disconnect_openvpn(vpn_process)

        save_session(session_file, processed_domains, [], screenshots_done, failed_domains, successful_domains_order, domain_urls, domain_titles, domain_status_codes, domain_body_excerpts)
        
        report_info_path = os.path.join(output_folder, "report_info.json")
        report_info = {
            "successful_domains_order": successful_domains_order,
            "domain_urls": domain_urls,
            "domain_titles": domain_titles
        }
        
        if get_csv_data:
            generate_csv(output_folder, successful_domains_order, domain_urls, domain_titles, domain_status_codes, domain_body_excerpts)
        try:
            with open(report_info_path, "w") as f:
                json.dump(report_info, f)
        except Exception as e:
            logging.getLogger('general_errors').error(f"Failed to save report info: {str(e)}")

        progress_bar_domains.close()
        progress_bar_screenshots.close()
        progress_bar_requests.close()
        
        if screenshots_done > 0 or len(successful_domains_order) > 0:
            print("\nGenerating report...")
            try:
                generate_report(output_folder)
            except Exception as e:
                logging.getLogger('general_errors').error(f"Failed to generate report: {str(e)}")
                print(f"Warning: Could not generate report: {str(e)}")



    else:
        print("All domains have been processed.")


def generate_csv(output_folder, successful_domains_order, domain_urls, domain_titles, domain_status_codes, domain_body_excerpts):
    import csv
    csv_path = os.path.join(output_folder, "report.csv")
    try:
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['site', 'status_code', 'title', 'body_excerpt'])
            
            for domain in successful_domains_order:
                status_code = domain_status_codes.get(domain, "")
                title = domain_titles.get(domain, "")
                body_excerpt = domain_body_excerpts.get(domain, "")
                writer.writerow([domain, status_code, title, body_excerpt])
        
        print(f"CSV report generated at: {csv_path}")
    except Exception as e:
        logging.getLogger('general_errors').error(f"Failed to generate CSV: {str(e)}")
        print(f"Warning: Could not generate CSV: {str(e)}")


def retry_failed_domains(session_file, output_folder, vpn_dir, max_requests, threads, timeout, webdriver_path, delay, vpn_mode, get_csv_data=False, accept_cookies=True):
    # Create screenshots subdirectory
    screenshots_folder = os.path.join(output_folder, "screenshots")
    os.makedirs(screenshots_folder, exist_ok=True)

    retry_file = f"{os.path.basename(session_file)}.retry.session"
    successful_domains_order = []
    domain_urls = {}
    domain_titles = {}
    domain_status_codes = {}
    domain_body_excerpts = {}
    
    main_session = load_session(session_file)
    if main_session:
        successful_domains_order = main_session.get("successful_domains_order", [])
        domain_urls = main_session.get("domain_urls", {})
        domain_titles = main_session.get("domain_titles", {})
        domain_status_codes = main_session.get("domain_status_codes", {})
        domain_body_excerpts = main_session.get("domain_body_excerpts", {})
    
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
                print(f"{len(remaining_domains)} domains are still failing. Retrying...")
            elif not remaining_domains and not failed_domains_set:
                print("All domains have been processed successfully after retry.")
                if os.path.exists(retry_file):
                    os.remove(retry_file)
                return False
            else:
                total_domains = len(remaining_domains) + len(processed_domains)
                print(f"Found a retry session with {len(remaining_domains)} domains.")
                print(f"Processed {len(processed_domains)}/{total_domains} so far, {screenshots_done} screenshots done.")
                while True:
                    try:
                        print("Continue? (y/n):")
                        choice = input().strip().lower()
                        if choice == 'y':
                            break
                        elif choice == 'n':
                            os.remove(retry_file)
                            return False
                        else:
                            print("Invalid input. Enter 'y' or 'n'.")
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
            print(f"{len(remaining_domains)} domains failed. Retrying.")
        progress_bar_domains = tqdm(total=total_domains, desc="Retrying domains / total", position=0, unit="dom")
        progress_bar_screenshots = tqdm(total=total_domains, desc="Screenshots done / total", position=1, unit="dom")
        progress_bar_requests = tqdm(total=max_requests if max_requests else 0, desc="Requests / total", position=2, unit="dom")
        progress_bar_domains.update(len(processed_domains))
        progress_bar_screenshots.update(screenshots_done)
        vpn_process = None
        ip_counter = 0
        with ThreadPoolExecutor(max_workers=threads) as executor:
            for i in range(0, len(remaining_domains), max_requests if max_requests else len(remaining_domains)):
                if vpn_mode == "none":
                    pass
                else:
                    connection_attempts = 0
                    connected = False
                    while not connected and connection_attempts < 5:
                        if vpn_process and vpn_mode == "openvpn":
                            disconnect_openvpn(vpn_process)
                            vpn_process = None
                        elif vpn_mode == "nordvpn":
                            subprocess.run(["nordvpn", "disconnect"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        if vpn_mode == "openvpn":
                            vpn_process = connect_openvpn(vpn_dir)
                            if vpn_process is None:
                                connection_attempts += 1
                                continue
                            old_ip = get_current_ip()
                            current_ip = wait_for_vpn_connection(old_ip=old_ip)
                            if current_ip:
                                connected = True
                                ip_counter += 1
                                tqdm.write(f"Connected with IP #{ip_counter}: {current_ip}")
                            else:
                                tqdm.write("OpenVPN connection failed. Retrying...")
                                connection_attempts += 1
                        elif vpn_mode == "nordvpn":
                            old_ip = get_current_ip()
                            ok = connect_nordvpn()
                            if not ok:
                                connection_attempts += 1
                                continue
                            current_ip = wait_for_vpn_connection(old_ip=old_ip)
                            if current_ip:
                                connected = True
                                ip_counter += 1
                                tqdm.write(f"Connected with NordVPN, IP #{ip_counter}: {current_ip}")
                            else:
                                tqdm.write("NordVPN connection failed. Retrying...")
                                connection_attempts += 1
                        time.sleep(delay)
                    if not connected:
                        tqdm.write("Could not connect to VPN after 5 attempts. Saving retry session and exiting...")
                        save_retry_session(retry_file, processed_domains, remaining_domains[i:], screenshots_done, list(failed_domains_set))
                        sys.exit(1)
                batch_domains = remaining_domains[i : i + (max_requests if max_requests else len(remaining_domains))]
                progress_bar_requests.reset()
                completed_requests = 0
                futures = {
                    executor.submit(take_screenshot, domain, output_folder, timeout, webdriver_path, get_csv_data, accept_cookies): domain
                    for domain in batch_domains
                }
                try:
                    for future in as_completed(futures):
                        domain = futures[future]
                        try:
                            result = future.result()
                            if len(result) == 5:
                                success, working_url, page_title, status_code, body_excerpt = result
                            elif len(result) == 3:
                                success, working_url, page_title = result
                                status_code, body_excerpt = None, ""
                            else:
                                success, working_url = result
                                page_title, status_code, body_excerpt = "", None, ""
                            processed_domains.append(domain)
                            progress_bar_domains.update(1)
                            progress_bar_requests.update(1)
                            completed_requests += 1
                            if success:
                                screenshots_done += 1
                                progress_bar_screenshots.update(1)
                                failed_domains_set.discard(domain)
                                if domain not in successful_domains_order:
                                    successful_domains_order.append(domain)
                                if working_url:
                                    domain_urls[domain] = working_url
                                if page_title:
                                    domain_titles[domain] = page_title
                                if get_csv_data:
                                    domain_status_codes[domain] = str(status_code) if status_code is not None else ""
                                    domain_body_excerpts[domain] = str(body_excerpt) if body_excerpt else ""
                            elif working_url:
                                failed_domains_set.discard(domain)
                                if domain not in successful_domains_order:
                                    successful_domains_order.append(domain)
                                if working_url:
                                    domain_urls[domain] = working_url
                                if page_title:
                                    domain_titles[domain] = page_title
                                if get_csv_data:
                                    domain_status_codes[domain] = str(status_code) if status_code is not None else ""
                                    domain_body_excerpts[domain] = str(body_excerpt) if body_excerpt else ""
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
                    if vpn_process and vpn_mode == "openvpn":
                        disconnect_openvpn(vpn_process)
                    elif vpn_mode == "nordvpn":
                        subprocess.run(["nordvpn", "disconnect"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    print(f"Retry session saved as '{retry_file}'.")
                    sys.exit(0)
                finally:
                    save_retry_session(
                        retry_file,
                        processed_domains,
                        remaining_domains[i + completed_requests:],
                        screenshots_done,
                        list(failed_domains_set)
                    )
                if vpn_mode == "openvpn" and vpn_process:
                    disconnect_openvpn(vpn_process)
                elif vpn_mode == "nordvpn":
                    subprocess.run(["nordvpn", "disconnect"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        progress_bar_domains.close()
        progress_bar_screenshots.close()
        progress_bar_requests.close()
        main_session = load_session(session_file)
        if main_session:
            main_session['failed_domains'] = list(failed_domains_set)
            save_session(session_file,
                         main_session.get('processed_domains', []),
                         main_session.get('remaining_domains', []),
                         main_session.get('screenshots_done', 0),
                         failed_domains_set,
                         successful_domains_order,
                         domain_urls,
                         domain_titles,
                         domain_status_codes,
                         domain_body_excerpts)
        else:
            save_session(session_file, [], [], 0, failed_domains_set, successful_domains_order, domain_urls, domain_titles, domain_status_codes, domain_body_excerpts)
        
        report_info_path = os.path.join(output_folder, "report_info.json")
        report_info = {
            "successful_domains_order": successful_domains_order,
            "domain_urls": domain_urls,
            "domain_titles": domain_titles
        }
        
        if get_csv_data:
            generate_csv(output_folder, successful_domains_order, domain_urls, domain_titles, domain_status_codes, domain_body_excerpts)
        try:
            with open(report_info_path, "w") as f:
                json.dump(report_info, f)
        except Exception as e:
            logging.getLogger('general_errors').error(f"Failed to save report info: {str(e)}")
        if failed_domains_set:
            print(f"{len(failed_domains_set)} domains still failing after retry.")
            while True:
                try:
                    print("Retry again? (y/n):")
                    retry_choice = input().strip().lower()
                    if retry_choice == 'y':
                        save_retry_session(
                            retry_file,
                            [],
                            list(failed_domains_set),
                            0,
                            []
                        )
                        break
                    elif retry_choice == 'n':
                        print("Retry skipped.")
                        if os.path.exists(retry_file):
                            os.remove(retry_file)
                        return False
                    else:
                        print("Invalid input. Enter 'y' or 'n'.")
                except KeyboardInterrupt:
                    print("\nOperation canceled by user.")
                    sys.exit(0)
        else:
            print("All domains have been processed successfully after retry.")
            if os.path.exists(retry_file):
                os.remove(retry_file)
            return False

def main():
    banner()
    parser = argparse.ArgumentParser(
        description="Domain screenshot tool with optional VPN rotation.",
        epilog="Target formats accepted in domains file or stdin:\n"
               "  - Full URL: https://example.com or http://example.com\n"
               "  - CIDR notation: 192.168.1.0/24 (expands to all IPs in range)\n"
               "  - IP address: 192.168.1.1 (tries both http and https)\n"
               "  - Domain name: example.com (tries https first, then http)\n"
               "Each target should be on a separate line.\n"
               "Use -s/--stdin to read from stdin (e.g., for piping from other tools).",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-m", "--vpn-mode", default="none", choices=["openvpn","nordvpn","none"], help="VPN mode: openvpn, nordvpn, or none (default: none)")
    parser.add_argument("-v", "--vpn-dir", help="Directory with .ovpn files (required if --vpn-mode=openvpn)")
    parser.add_argument("-d", "--domains", help="File containing the domain list (one target per line)")
    parser.add_argument("-s", "--stdin", action="store_true", help="Read targets from stdin instead of a file")
    parser.add_argument("-o", "--output", required=True, dest="screenshot_dir", help="Screenshot output folder")
    parser.add_argument("-t", "--threads", type=int, required=True, help="Number of threads")
    parser.add_argument("-T", "--timeout", type=int, required=True, help="Page load timeout (in seconds)")
    parser.add_argument("-n", "--max-requests", type=int, help="Max requests before changing IP (required if using VPN)")
    parser.add_argument("-D", "--delay", type=int, default=0, help="Delay (in seconds) before connecting to the new VPN (default: 0)")
    parser.add_argument("-c", "--csv", action="store_true", help="Generate a CSV file with domain, status code, title, and body excerpt")
    parser.add_argument("--no-cookie-accept", action="store_true", help="Disable automatic cookie consent banner acceptance (enabled by default)")
    args = parser.parse_args()
    if args.vpn_mode == "none":
        if args.max_requests:
            print("Error: -n / --max-requests can only be used if you are using a VPN (--vpn-mode=openvpn or --vpn-mode=nordvpn).")
            sys.exit(1)
        args.max_requests = 0
    else:
        if not args.max_requests or args.max_requests < 1:
            print("Error: -n / --max-requests is required and must be > 0 when using a VPN.")
            sys.exit(1)
    if args.vpn_mode == "openvpn":
        if not args.vpn_dir:
            print("Error: -v / --vpn-dir is required if you use --vpn-mode=openvpn.")
            sys.exit(1)
        if not os.path.exists(args.vpn_dir):
            error_message = f"VPN directory '{args.vpn_dir}' does not exist."
            print(f"Error: {error_message}")
            logging.getLogger('general_errors').error(error_message)
            sys.exit(1)
        ovpn_files = [f for f in os.listdir(args.vpn_dir) if f.endswith(".ovpn")]
        if not ovpn_files:
            error_message = f"No .ovpn files found in '{args.vpn_dir}'."
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
    
    if args.stdin:
        if args.domains:
            error_message = "Cannot use both -s/--stdin and -d/--domains. Use one or the other."
            print(f"Error: {error_message}")
            logging.getLogger('general_errors').error(error_message)
            sys.exit(1)
        try:
            domains = [line.strip() for line in sys.stdin if line.strip()]
        except Exception as e:
            error_message = f"Error reading from stdin: {str(e)}"
            print(f"Error: {error_message}")
            logging.getLogger('general_errors').error(error_message)
            sys.exit(1)
        session_file = f"stdin_{os.path.basename(args.screenshot_dir)}.session"
    else:
        if not args.domains:
            error_message = "Either -d/--domains or -s/--stdin must be specified."
            print(f"Error: {error_message}")
            logging.getLogger('general_errors').error(error_message)
            sys.exit(1)
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
        session_file = f"{os.path.basename(args.domains)}_{os.path.basename(args.screenshot_dir)}.session"
    
    if not domains:
        error_message = "No domains found."
        print(f"Error: {error_message}")
        logging.getLogger('general_errors').error(error_message)
        sys.exit(1)
    domains = list(set(domains))
    try:
        accept_cookies = not args.no_cookie_accept
        process_domains(domains, args.screenshot_dir, args.vpn_dir if args.vpn_dir else "", args.max_requests, args.threads, args.timeout, webdriver_path, session_file, args.delay, args.vpn_mode, args.csv, accept_cookies)
    except KeyboardInterrupt:
        print("\nOperation canceled by user.")
        sys.exit(0)
    except Exception as e:
        error_message = f"Unexpected error: {str(e)}"
        print(f"Error: {error_message}")
        logging.getLogger('general_errors').error(error_message)
        sys.exit(1)
    session = load_session(session_file)
    if session and session.get("failed_domains"):
        failed_domains = session["failed_domains"]
        print(f"{len(failed_domains)} domains failed.")
        while True:
            print("Retry? (y/n):")
            try:
                retry_choice = input().strip().lower()
                if retry_choice == 'y':
                    accept_cookies = not args.no_cookie_accept
                    continue_retry = retry_failed_domains(session_file, args.screenshot_dir, args.vpn_dir if args.vpn_dir else "", args.max_requests, args.threads, args.timeout, webdriver_path, args.delay, args.vpn_mode, args.csv, accept_cookies)
                    if not continue_retry:
                        break
                    session = load_session(session_file)
                    failed_domains = set(session.get("failed_domains", []))
                    if failed_domains:
                        print(f"{len(failed_domains)} domains still failing after retry.")
                    else:
                        print("All domains have been processed successfully after retry.")
                        session = load_session(session_file)
                        if session and (session.get("screenshots_done", 0) > 0 or len(session.get("successful_domains_order", [])) > 0):
                            print("\nGenerating report...")
                            try:
                                generate_report(args.screenshot_dir)
                            except Exception as e:
                                logging.getLogger('general_errors').error(f"Failed to generate report: {str(e)}")
                                print(f"Warning: Could not generate report: {str(e)}")
                            if args.csv:
                                successful_domains_order = session.get("successful_domains_order", [])
                                domain_urls = session.get("domain_urls", {})
                                domain_titles = session.get("domain_titles", {})
                                domain_status_codes = session.get("domain_status_codes", {})
                                domain_body_excerpts = session.get("domain_body_excerpts", {})
                                generate_csv(args.screenshot_dir, successful_domains_order, domain_urls, domain_titles, domain_status_codes, domain_body_excerpts)
                        break
                elif retry_choice == 'n':
                    print("Retry skipped.")
                    break
                else:
                    print("Invalid input. Enter 'y' or 'n'.")
            except KeyboardInterrupt:
                print("\nOperation canceled by user.")
                sys.exit(0)
    else:
        print("Process completed.")

if __name__ == "__main__":
    main()
