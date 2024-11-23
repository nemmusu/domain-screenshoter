import os
from PIL import Image
import imagehash

def generate_report(output_folder, columns=4):
    report_path = os.path.join(output_folder, "report.html")
    image_files = [f for f in os.listdir(output_folder) if f.endswith(".png")]
    if not image_files:
        print("No screenshots found in the specified directory.")
        return

    # Pre-calculating hashes for all images
    image_hashes = {}
    for img in image_files:
        try:
            img_path = os.path.join(output_folder, img)
            img_hash = str(imagehash.average_hash(Image.open(img_path)))
            image_hashes[img] = img_hash
        except Exception as e:
            print(f"Failed to process image {img}: {e}")

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Screenshot Report - {os.path.basename(output_folder)}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f4f4f4;
            }}
            .header {{
                position: sticky;
                top: 0;
                background-color: #fff;
                z-index: 1000;
                padding: 10px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                text-align: center;
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
                color: #007BFF;
            }}
            .container {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                gap: 10px;
                padding: 10px;
            }}
            .container div {{
                text-align: center;
                position: relative;
            }}
            .container img {{
                width: 100%;
                height: auto;
                max-height: 150px;
                object-fit: contain;
                cursor: pointer;
                border: 2px solid #ddd;
                border-radius: 4px;
            }}
            .container img:hover {{
                border-color: #007BFF;
            }}
            .domain {{
                display: block;
                font-size: 0.85em;
                color: #333;
                text-decoration: none;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }}
            .domain:hover {{
                text-decoration: underline;
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
            }}
            .context-menu button {{
                padding: 10px;
                border: none;
                background: none;
                text-align: left;
                cursor: pointer;
                width: 100%;
            }}
            .context-menu button:hover {{
                background-color: #f4f4f4;
            }}
            .modal {{
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.8);
                z-index: 2000;
                justify-content: center;
                align-items: center;
                flex-direction: column;
                gap: 10px;
            }}
            .modal-content {{
                position: relative;
                max-width: 70%;
                max-height: 70%;
                text-align: center;
            }}
            .modal-content img {{
                max-width: 100%;
                max-height: 100%;
                width: auto;
                height: auto;
                object-fit: contain;
                border: 2px solid #ddd;
                border-radius: 4px;
            }}
            .modal-close {{
                position: absolute;
                top: 10px;
                right: 10px;
                font-size: 24px;
                color: #ff0000;
                cursor: pointer;
                background: none;
                border: none;
                z-index: 3000;
            }}
            .modal-close:hover {{
                color: #ff5555;
            }}
            .modal-link {{
                display: block;
                color: #007BFF;
                font-size: 16px;
                margin-top: 10px;
                text-decoration: none;
            }}
            .modal-link:hover {{
                text-decoration: underline;
            }}
            .arrow {{
                position: absolute;
                top: 50%;
                font-size: 36px;
                color: #fff;
                cursor: pointer;
                user-select: none;
                z-index: 3000;
            }}
            .arrow:hover {{
                color: #ff5555;
            }}
            .arrow.left {{
                left: 10px;
            }}
            .arrow.right {{
                right: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Screenshot Report - {os.path.basename(output_folder)}</h1>
            <div id="filter-info" class="filter-info hidden"></div>
        </div>
        <div class="container">
    """

    for img, img_hash in image_hashes.items():
        domain = os.path.splitext(img)[0]
        truncated_domain = domain if len(domain) <= 20 else domain[:20] + "..."
        html_content += f"""
            <div>
                <img src="{img}" alt="{domain}" data-hash="{img_hash}">
                <a class="domain" href="http://{domain}" title="{domain}" target="_blank">{truncated_domain}</a>
            </div>
        """

    html_content += """
        </div>
        <div class="modal" id="modal">
            <span class="arrow left" onclick="navigate(-1)">&#10094;</span>
            <div class="modal-content">
                <button class="modal-close" onclick="closeModal()">×</button>
                <img id="modal-image" src="" alt="Image">
                <a id="modal-link" class="modal-link" href="#" target="_blank"></a>
            </div>
            <span class="arrow right" onclick="navigate(1)">&#10095;</span>
        </div>
        <div class="context-menu" id="context-menu">
            <button onclick="excludeImages()">Exclude all matching images</button>
        </div>
        <script>
            let contextMenu = document.getElementById("context-menu");
            let selectedHash = "";
            let filters = new Set();
            let filterInfo = document.getElementById("filter-info");
            let modal = document.getElementById("modal");
            let modalImage = document.getElementById("modal-image");
            let modalLink = document.getElementById("modal-link");
            let images = Array.from(document.querySelectorAll(".container img"));
            let filteredImages = images;
            let currentIndex = -1;

            function openModal(index) {
                currentIndex = index;
                const img = filteredImages[currentIndex];
                modal.style.display = "flex";
                modalImage.src = img.src;
                modalLink.href = img.nextElementSibling.href;
                modalLink.textContent = img.nextElementSibling.href;
            }

            function closeModal() {
                modal.style.display = "none";
                currentIndex = -1;
            }

            function navigate(direction) {
                if (currentIndex === -1) return;
                currentIndex = (currentIndex + direction + filteredImages.length) % filteredImages.length;
                openModal(currentIndex);
            }

            document.addEventListener("keydown", function(event) {
                if (modal.style.display === "flex") {
                    if (event.key === "ArrowLeft") navigate(-1);
                    if (event.key === "ArrowRight") navigate(1);
                    if (event.key === "Escape") closeModal();
                }
            });

            images.forEach((img, index) => {
                img.addEventListener("click", () => openModal(index));
            });

            function excludeImages() {
                const images = document.querySelectorAll(`img[data-hash='${selectedHash}']`);
                images.forEach(img => img.parentElement.classList.add("hidden"));
                if (!filters.has(selectedHash)) {
                    filters.add(selectedHash);
                    addFilterInfo(selectedHash, images[0].src);
                }
                contextMenu.style.display = "none";
                updateFilteredImages();
            }

            function addFilterInfo(hash, src) {
                filterInfo.classList.remove("hidden");
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
                document.querySelectorAll(`.hidden img[data-hash='${hash}']`).forEach(img => img.parentElement.classList.remove("hidden"));
                if (filters.size === 0) {
                    filterInfo.classList.add("hidden");
                }
                updateFilteredImages();
            }

            function updateFilteredImages() {
                filteredImages = filters.size
                    ? images.filter(img => !img.parentElement.classList.contains("hidden"))
                    : images;
            }

            document.addEventListener("contextmenu", function(event) {
                let target = event.target;
                if (target.tagName === "IMG") {
                    event.preventDefault();
                    selectedHash = target.getAttribute("data-hash");
                    contextMenu.style.top = `${event.pageY}px`;
                    contextMenu.style.left = `${event.pageX}px`;
                    contextMenu.style.display = "flex";
                }
            });

            document.addEventListener("click", function(event) {
                if (!event.target.closest(".context-menu")) {
                    contextMenu.style.display = "none";
                }
            });

            updateFilteredImages();
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
