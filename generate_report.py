import os
import json
import html
from PIL import Image
import imagehash
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

def generate_report(output_folder, columns=4):
    report_path = os.path.join(output_folder, "report.html")
    image_files = [f for f in os.listdir(output_folder) if f.endswith(".png")]
    if not image_files:
        print("No screenshots found in the specified directory.")
        return
    
    # Carica le informazioni sull'ordine e gli URL
    report_info_path = os.path.join(output_folder, "report_info.json")
    successful_domains_order = []
    domain_urls = {}
    
    if os.path.exists(report_info_path):
        try:
            with open(report_info_path, "r") as f:
                report_info = json.load(f)
                successful_domains_order = report_info.get("successful_domains_order", [])
                domain_urls = report_info.get("domain_urls", {})
        except Exception as e:
            print(f"Warning: Could not load report info: {e}")

    def compute_hash(img):
        img_path = os.path.join(output_folder, img)
        try:
            img_hash = str(imagehash.average_hash(Image.open(img_path)))
            return img, img_hash
        except Exception as e:
            print(f"Failed to process image {img}: {e}")
            return img, None

    image_hashes = {}
    with ThreadPoolExecutor() as executor:
        results = list(tqdm(executor.map(compute_hash, image_files), total=len(image_files), desc="Processing images"))

    for img, img_hash in results:
        if img_hash is not None:
            image_hashes[img] = img_hash
    
    # Ordina le immagini secondo l'ordine di processamento
    # Crea un mapping filename -> dominio
    filename_to_domain = {}
    for img in image_files:
        domain = os.path.splitext(img)[0]
        filename_to_domain[img] = domain
    
    # Ordina secondo successful_domains_order, poi aggiungi quelli non in ordine
    ordered_images = []
    seen_domains = set()
    
    # Prima aggiungi quelli nell'ordine corretto
    for domain in successful_domains_order:
        # Trova il file immagine corrispondente
        for img in image_files:
            img_domain = os.path.splitext(img)[0]
            if img_domain == domain and img not in ordered_images:
                ordered_images.append(img)
                seen_domains.add(domain)
                break
    
    # Poi aggiungi quelli non nell'ordine
    for img in image_files:
        if img not in ordered_images:
            ordered_images.append(img)

    # Crea la lista dei domini per la sidebar
    sidebar_domains = []
    for img in ordered_images:
        if img in image_hashes:
            domain = os.path.splitext(img)[0]
            domain_url = domain_urls.get(domain, f"https://{domain}")
            if not domain_url.startswith(("http://", "https://")):
                domain_url = f"https://{domain_url}"
            sidebar_domains.append({
                'domain': domain,
                'url': domain_url,
                'img': img
            })

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Screenshot Report - {os.path.basename(output_folder)}</title>
        <style>
            * {{
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f5f5f5;
                display: flex;
                flex-direction: column;
                height: 100vh;
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                z-index: 1000;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: 600;
            }}
            .header .stats {{
                margin-top: 10px;
                font-size: 14px;
                opacity: 0.9;
            }}
            .main-container {{
                display: flex;
                flex: 1;
                overflow: hidden;
            }}
            .sidebar {{
                width: 300px;
                background-color: #fff;
                border-right: 1px solid #e0e0e0;
                overflow-y: auto;
                padding: 20px;
                box-shadow: 2px 0 5px rgba(0,0,0,0.05);
            }}
            .sidebar h2 {{
                margin: 0 0 15px 0;
                font-size: 18px;
                color: #333;
                font-weight: 600;
            }}
            .search-box {{
                width: 100%;
                padding: 10px;
                margin-bottom: 15px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 14px;
                box-sizing: border-box;
            }}
            .search-box:focus {{
                outline: none;
                border-color: #667eea;
            }}
            .domain-count {{
                font-size: 12px;
                color: #666;
                margin-bottom: 10px;
            }}
            .domain-list {{
                list-style: none;
                padding: 0;
                margin: 0;
            }}
            .domain-item {{
                padding: 12px;
                margin-bottom: 8px;
                background-color: #f8f9fa;
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.2s;
                border: 2px solid transparent;
            }}
            .domain-item:hover {{
                background-color: #e9ecef;
                border-color: #667eea;
                transform: translateX(5px);
            }}
            .domain-item.active {{
                background-color: #667eea;
                color: white;
                border-color: #667eea;
            }}
            .domain-item.active .domain-name {{
                color: white;
            }}
            .domain-item.active .domain-url {{
                color: rgba(255,255,255,0.9);
            }}
            .domain-name {{
                font-weight: 600;
                color: #333;
                margin-bottom: 4px;
                font-size: 14px;
            }}
            .domain-url {{
                font-size: 12px;
                color: #666;
                text-decoration: none;
                word-break: break-all;
            }}
            .domain-url:hover {{
                text-decoration: underline;
            }}
            .gallery-container {{
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .gallery {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 20px;
            }}
            .gallery-item {{
                background: white;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                transition: transform 0.2s, box-shadow 0.2s;
                cursor: pointer;
            }}
            .gallery-item:hover {{
                transform: translateY(-5px);
                box-shadow: 0 4px 16px rgba(0,0,0,0.15);
            }}
            .gallery-item img {{
                width: 100%;
                height: auto;
                display: block;
                max-height: 250px;
                object-fit: contain;
                background: #f8f9fa;
                loading: lazy;
            }}
            .gallery-item .caption {{
                padding: 12px;
                text-align: center;
            }}
            .gallery-item .caption .domain-name {{
                font-weight: 600;
                color: #333;
                font-size: 14px;
                margin-bottom: 4px;
            }}
            .gallery-item .caption .domain-url {{
                font-size: 12px;
                color: #667eea;
                text-decoration: none;
            }}
            .gallery-item .caption .domain-url:hover {{
                text-decoration: underline;
            }}
            .modal {{
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.95);
                z-index: 2000;
                justify-content: center;
                align-items: center;
                flex-direction: column;
            }}
            .modal.active {{
                display: flex;
            }}
            .modal-content {{
                position: relative;
                max-width: 90%;
                max-height: 90%;
                text-align: center;
                background: white;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            }}
            .modal-content img {{
                max-width: 100%;
                max-height: calc(90vh - 120px);
                width: auto;
                height: auto;
                object-fit: contain;
                border-radius: 8px;
            }}
            .modal-info {{
                margin-top: 15px;
                padding-top: 15px;
                border-top: 1px solid #e0e0e0;
            }}
            .modal-info .domain-name {{
                font-size: 18px;
                font-weight: 600;
                color: #333;
                margin-bottom: 8px;
            }}
            .modal-info .domain-url {{
                font-size: 14px;
                color: #667eea;
                text-decoration: none;
            }}
            .modal-info .domain-url:hover {{
                text-decoration: underline;
            }}
            .modal-close {{
                position: absolute;
                top: 15px;
                right: 15px;
                width: 40px;
                height: 40px;
                background: rgba(255,255,255,0.9);
                border: none;
                border-radius: 50%;
                font-size: 24px;
                color: #333;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s;
                z-index: 3000;
            }}
            .modal-close:hover {{
                background: white;
                transform: scale(1.1);
            }}
            .arrow {{
                position: absolute;
                top: 50%;
                transform: translateY(-50%);
                width: 50px;
                height: 50px;
                background: rgba(255,255,255,0.9);
                border: none;
                border-radius: 50%;
                font-size: 28px;
                color: #333;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s;
                z-index: 3000;
                box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            }}
            .arrow:hover {{
                background: white;
                transform: translateY(-50%) scale(1.1);
            }}
            .arrow.left {{
                left: 20px;
            }}
            .arrow.right {{
                right: 20px;
            }}
            .arrow:disabled {{
                opacity: 0.3;
                cursor: not-allowed;
            }}
            .hidden {{
                display: none !important;
            }}
            .context-menu {{
                position: absolute;
                background-color: #fff;
                border: 1px solid #ccc;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                z-index: 1000;
                display: none;
                flex-direction: column;
                width: 200px;
                border-radius: 8px;
                overflow: hidden;
            }}
            .context-menu button {{
                padding: 12px;
                border: none;
                background: none;
                text-align: left;
                cursor: pointer;
                width: 100%;
                transition: background 0.2s;
            }}
            .context-menu button:hover {{
                background-color: #f4f4f4;
            }}
            .filter-info {{
                display: flex;
                align-items: center;
                justify-content: start;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 10px;
                padding: 10px;
            }}
            .filter-info .filter-item {{
                display: flex;
                align-items: center;
                gap: 5px;
                background: #f8f9fa;
                padding: 8px 12px;
                border-radius: 8px;
            }}
            .filter-info img {{
                width: 50px;
                height: auto;
                border: 2px solid #ddd;
                border-radius: 4px;
            }}
            .filter-info button {{
                background: none;
                border: none;
                font-size: 16px;
                cursor: pointer;
                color: #667eea;
            }}
            @media (max-width: 768px) {{
                .main-container {{
                    flex-direction: column;
                }}
                .sidebar {{
                    width: 100%;
                    max-height: 200px;
                    border-right: none;
                    border-bottom: 1px solid #e0e0e0;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📸 Screenshot Report - {html.escape(os.path.basename(output_folder))}</h1>
            <div class="stats">Total: {len(ordered_images)} screenshots</div>
        </div>
        <div class="main-container">
            <div class="sidebar">
                <h2>🌐 Domains ({len(sidebar_domains)})</h2>
                <input type="text" class="search-box" id="domain-search" placeholder="🔍 Search domains...">
                <div class="domain-count" id="domain-count">Showing {len(sidebar_domains)} domains</div>
                <ul class="domain-list" id="domain-list">
    """

    # Aggiungi i domini alla sidebar
    for idx, domain_info in enumerate(sidebar_domains):
        domain = domain_info['domain']
        domain_url = domain_info['url']
        img = domain_info['img']
        truncated_domain = domain if len(domain) <= 25 else domain[:25] + "..."
        
        html_content += f"""
                    <li class="domain-item" data-img="{html.escape(img)}" data-index="{idx}">
                        <div class="domain-name">{html.escape(truncated_domain)}</div>
                        <a href="{html.escape(domain_url)}" class="domain-url" target="_blank" onclick="event.stopPropagation()">{html.escape(domain_url)}</a>
                    </li>
        """

    html_content += """
                </ul>
            </div>
            <div class="gallery-container">
                <div class="gallery" id="gallery">
    """

    # Aggiungi le immagini alla galleria
    for img in ordered_images:
        if img not in image_hashes:
            continue
        img_hash = image_hashes[img]
        domain = os.path.splitext(img)[0]
        truncated_domain = domain if len(domain) <= 20 else domain[:20] + "..."
        
        # Usa l'URL corretto (http o https) se disponibile, altrimenti default a https
        domain_url = domain_urls.get(domain, f"https://{domain}")
        # Se domain_url non inizia con http:// o https://, aggiungilo
        if not domain_url.startswith(("http://", "https://")):
            domain_url = f"https://{domain_url}"
        
        domain_url_escaped = html.escape(domain_url)
        
        html_content += f"""
                    <div class="gallery-item" data-img="{html.escape(img)}" data-domain="{html.escape(domain)}">
                        <img src="{html.escape(img)}" alt="{html.escape(domain)}" data-hash="{img_hash}" loading="lazy">
                        <div class="caption">
                            <div class="domain-name">{html.escape(truncated_domain)}</div>
                            <a href="{domain_url_escaped}" class="domain-url" target="_blank">{html.escape(truncated_domain)}</a>
                        </div>
                    </div>
        """

    html_content += """
                </div>
            </div>
        </div>
        <div class="modal" id="modal">
            <span class="arrow left" id="arrow-left">‹</span>
            <div class="modal-content">
                <button class="modal-close" id="modal-close-btn">×</button>
                <img id="modal-image" src="" alt="Image">
                <div class="modal-info">
                    <div class="domain-name" id="modal-domain-name"></div>
                    <a href="#" class="domain-url" id="modal-domain-url" target="_blank"></a>
                </div>
            </div>
            <span class="arrow right" id="arrow-right">›</span>
        </div>
        <script>
            (function() {
            let modal = document.getElementById("modal");
            let modalImage = document.getElementById("modal-image");
            let modalDomainName = document.getElementById("modal-domain-name");
            let modalDomainUrl = document.getElementById("modal-domain-url");
            let currentIndex = -1;
            let allImages = [];
            let domainItems = [];
            let contextMenu = null;
            let selectedHash = "";
            let filters = new Set();
            
            function init() {
                allImages = Array.from(document.querySelectorAll(".gallery-item img"));
                domainItems = Array.from(document.querySelectorAll(".domain-item"));
                console.log("Initialized:", allImages.length, "images,", domainItems.length, "domain items");
            }

            function getVisibleImages() {
                return allImages.filter(img => {
                    let item = img.closest(".gallery-item");
                    return item && !item.classList.contains("hidden");
                });
            }

            function openModal(imgElement) {
                if (!imgElement) return;
                const visibleImages = getVisibleImages();
                currentIndex = visibleImages.findIndex(img => img === imgElement);
                if (currentIndex === -1 && visibleImages.length > 0) {
                    // Se non trovato, prova a trovare per src
                    const imgSrc = imgElement.src || imgElement.getAttribute("src");
                    currentIndex = visibleImages.findIndex(img => {
                        const item = img.closest(".gallery-item");
                        return item && item.getAttribute("data-img") && imgSrc.includes(item.getAttribute("data-img"));
                    });
                }
                if (currentIndex === -1 && visibleImages.length > 0) {
                    currentIndex = 0;
                }
                if (currentIndex >= 0) {
                    showModalImage(currentIndex);
                    modal.classList.add("active");
                    updateActiveDomain();
                }
            }

            function closeModal() {
                modal.classList.remove("active");
                currentIndex = -1;
                updateActiveDomain();
            }

            function navigate(direction) {
                const visibleImages = getVisibleImages();
                if (currentIndex === -1 || visibleImages.length === 0) return;
                currentIndex = (currentIndex + direction + visibleImages.length) % visibleImages.length;
                showModalImage(currentIndex);
                updateActiveDomain();
            }

            function showModalImage(index) {
                const visibleImages = getVisibleImages();
                if (index < 0 || index >= visibleImages.length) return;
                const img = visibleImages[index];
                const galleryItem = img.closest(".gallery-item");
                const domain = galleryItem.getAttribute("data-domain");
                const imgSrc = galleryItem.getAttribute("data-img");
                
                modalImage.src = imgSrc;
                modalDomainName.textContent = domain;
                
                // Trova l'URL dal link nella caption
                const urlLink = galleryItem.querySelector(".domain-url");
                if (urlLink) {
                    modalDomainUrl.href = urlLink.getAttribute("href");
                    modalDomainUrl.textContent = urlLink.getAttribute("href");
                }
                
                // Scroll nella sidebar
                scrollToDomain(domain);
            }

            function updateActiveDomain() {
                if (currentIndex === -1) {
                    domainItems.forEach(item => item.classList.remove("active"));
                    return;
                }
                const visibleImages = getVisibleImages();
                if (currentIndex >= 0 && currentIndex < visibleImages.length) {
                    const img = visibleImages[currentIndex];
                    const galleryItem = img.closest(".gallery-item");
                    const imgSrc = galleryItem.getAttribute("data-img");
                    
                    domainItems.forEach(item => {
                        if (item.getAttribute("data-img") === imgSrc) {
                            item.classList.add("active");
                        } else {
                            item.classList.remove("active");
                        }
                    });
                }
            }

            function scrollToDomain(domain) {
                domainItems.forEach(item => {
                    const dataImg = item.getAttribute("data-img");
                    const domainName = item.querySelector(".domain-name");
                    if ((dataImg && dataImg.startsWith(domain.replace(/[^a-zA-Z0-9._-]/g, "_"))) ||
                        (domainName && domainName.textContent.includes(domain))) {
                        item.scrollIntoView({ behavior: "smooth", block: "center" });
                    }
                });
            }

            // Context menu per escludere immagini simili
            function createContextMenu() {
                if (!contextMenu) {
                    contextMenu = document.createElement("div");
                    contextMenu.className = "context-menu";
                    contextMenu.id = "context-menu";
                    const button = document.createElement("button");
                    button.textContent = "Exclude all matching images";
                    button.onclick = excludeImages;
                    contextMenu.appendChild(button);
                    document.body.appendChild(contextMenu);
                }
                return contextMenu;
            }

            function excludeImages() {
                const imagesToHide = document.querySelectorAll(`img[data-hash='${selectedHash}']`);
                imagesToHide.forEach(img => {
                    const item = img.closest(".gallery-item");
                    if (item) {
                        item.classList.add("hidden");
                    }
                });
                if (!filters.has(selectedHash)) {
                    filters.add(selectedHash);
                    addFilterInfo(selectedHash, imagesToHide[0].src);
                }
                if (contextMenu) {
                    contextMenu.style.display = "none";
                }
            }

            function addFilterInfo(hash, src) {
                let filterInfo = document.getElementById("filter-info");
                if (!filterInfo) {
                    filterInfo = document.createElement("div");
                    filterInfo.id = "filter-info";
                    filterInfo.className = "filter-info";
                    document.querySelector(".header").appendChild(filterInfo);
                }
                const filterItem = document.createElement("div");
                filterItem.className = "filter-item";
                filterItem.dataset.hash = hash;
                filterItem.innerHTML = `
                    <img src="${src}" alt="Filter">
                    <button onclick="removeFilter('${hash}')">X</button>
                `;
                filterInfo.appendChild(filterItem);
            }

            function removeFilter(hash) {
                filters.delete(hash);
                document.querySelectorAll(`.filter-item[data-hash='${hash}']`).forEach(item => item.remove());
                document.querySelectorAll(`.hidden img[data-hash='${hash}']`).forEach(img => {
                    const item = img.closest(".gallery-item");
                    if (item) {
                        item.classList.remove("hidden");
                    }
                });
                const filterInfo = document.getElementById("filter-info");
                if (filterInfo && filterInfo.children.length === 0) {
                    filterInfo.remove();
                }
            }


            document.addEventListener("click", function(event) {
                if (contextMenu && !event.target.closest(".context-menu")) {
                    contextMenu.style.display = "none";
                }
            });

            // Tastiera
            document.addEventListener("keydown", function(event) {
                if (modal.classList.contains("active")) {
                    if (event.key === "ArrowLeft") navigate(-1);
                    if (event.key === "ArrowRight") navigate(1);
                    if (event.key === "Escape") closeModal();
                }
            });

            // Click fuori dal modal per chiudere
            modal.addEventListener("click", function(event) {
                if (event.target === modal) {
                    closeModal();
                }
            });

            // Funzione globale per removeFilter (chiamata dal filter button)
            window.removeFilter = removeFilter;
            
            // Rendi le funzioni globali per gli onclick
            window.navigate = navigate;
            window.closeModal = closeModal;
            
            // Funzione per filtrare i domini nella sidebar
            function filterDomains(searchTerm) {
                const searchLower = searchTerm.toLowerCase();
                let visibleCount = 0;
                
                domainItems.forEach(item => {
                    const domainName = item.querySelector(".domain-name");
                    const domainUrl = item.querySelector(".domain-url");
                    const text = (domainName ? domainName.textContent : "") + " " + (domainUrl ? domainUrl.textContent : "");
                    const matches = text.toLowerCase().includes(searchLower);
                    
                    if (matches) {
                        item.style.display = "";
                        visibleCount++;
                    } else {
                        item.style.display = "none";
                    }
                });
                
                const countEl = document.getElementById("domain-count");
                if (countEl) {
                    countEl.textContent = `Showing ${visibleCount} of ${domainItems.length} domains`;
                }
            }
            
            // Inizializza quando il DOM è pronto
            function setup() {
                init();
                
                // Barra di ricerca per i domini
                const searchBox = document.getElementById("domain-search");
                if (searchBox) {
                    searchBox.addEventListener("input", function(e) {
                        filterDomains(e.target.value);
                    });
                }
                
                // Event delegation per la galleria
                const gallery = document.getElementById("gallery");
                if (gallery) {
                    gallery.addEventListener("click", function(e) {
                        const galleryItem = e.target.closest(".gallery-item");
                        if (!galleryItem) return;
                        
                        // Non aprire se si clicca sul link
                        if (e.target.tagName === "A" || e.target.closest("a")) {
                            return;
                        }
                        
                        e.stopPropagation();
                        console.log("Click on gallery item:", galleryItem);
                        const img = galleryItem.querySelector("img");
                        if (img) {
                            openModal(img);
                        }
                    }, true);
                    
                    // Imposta cursor pointer su tutti gli item
                    document.querySelectorAll(".gallery-item").forEach(item => {
                        item.style.cursor = "pointer";
                    });
                } else {
                    console.error("Gallery not found!");
                }

                // Event delegation per la sidebar
                const domainList = document.getElementById("domain-list");
                if (domainList) {
                    domainList.addEventListener("click", function(e) {
                        const domainItem = e.target.closest(".domain-item");
                        if (!domainItem) return;
                        
                        // Non aprire se si clicca sul link URL
                        if (e.target.tagName === "A" || e.target.closest("a")) {
                            return;
                        }
                        
                        e.stopPropagation();
                        console.log("Click on domain item:", domainItem);
                        const imgSrc = domainItem.getAttribute("data-img");
                        if (imgSrc) {
                            const galleryItem = document.querySelector(`.gallery-item[data-img="${imgSrc}"]`);
                            if (galleryItem) {
                                const img = galleryItem.querySelector("img");
                                if (img) {
                                    openModal(img);
                                    // Scroll alla gallery item
                                    galleryItem.scrollIntoView({ behavior: "smooth", block: "center" });
                                }
                            }
                        }
                    }, true);
                    
                    // Imposta cursor pointer su tutti gli item
                    document.querySelectorAll(".domain-item").forEach(item => {
                        item.style.cursor = "pointer";
                    });
                } else {
                    console.error("Domain list not found!");
                }
                
                // Tasto destro per escludere immagini simili
                if (gallery) {
                    gallery.addEventListener("contextmenu", function(event) {
                        let target = event.target;
                        if (target.tagName === "IMG" && target.closest(".gallery-item")) {
                            event.preventDefault();
                            event.stopPropagation();
                            event.stopImmediatePropagation();
                            selectedHash = target.getAttribute("data-hash");
                            console.log("Context menu on image, hash:", selectedHash);
                            if (selectedHash) {
                                const menu = createContextMenu();
                                menu.style.top = `${event.pageY}px`;
                                menu.style.left = `${event.pageX}px`;
                                menu.style.display = "flex";
                                menu.style.position = "fixed";
                                menu.style.zIndex = "10000";
                            }
                            return false;
                        }
                    }, true);
                }
                
                // Aggiungi event listener per le frecce e il pulsante di chiusura
                const arrowLeft = document.getElementById("arrow-left");
                const arrowRight = document.getElementById("arrow-right");
                const closeBtn = document.getElementById("modal-close-btn");
                
                if (arrowLeft) {
                    arrowLeft.addEventListener("click", function() { navigate(-1); });
                }
                if (arrowRight) {
                    arrowRight.addEventListener("click", function() { navigate(1); });
                }
                if (closeBtn) {
                    closeBtn.addEventListener("click", function() { closeModal(); });
                }
            }
            
            // Inizializza quando il DOM è pronto
            if (document.readyState === "loading") {
                document.addEventListener("DOMContentLoaded", setup);
            } else {
                setup();
            }
            
            })(); // Fine IIFE
        </script>
    </body>
    </html>
    """

    with open(report_path, "w", encoding="utf-8") as report_file:
        report_file.write(html_content)

    print(f"Report generated at: {report_path}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate an HTML report for screenshots.")
    parser.add_argument("-o", "--output-folder", required=True, help="Directory containing screenshots.")
    args = parser.parse_args()

    generate_report(args.output_folder)
