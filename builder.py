import cloudscraper
from bs4 import BeautifulSoup
import json
import re
import os

# Configurazione URL base
BASE_URL = "https://www.animeworld.ac"
UPDATED_URL = f"{BASE_URL}/updated"

def get_id_from_link(link):
    """
    Estrae l'ID univoco dal link di AnimeWorld.
    Esempio: /play/nome-anime.1234/ep-1 -> aw_1234
    """
    try:
        # Cerca il pattern .ID/
        match = re.search(r'\.([a-zA-Z0-9]+)/', link)
        if match:
            return f"aw_{match.group(1)}"
        # Fallback se il link è diverso
        return f"aw_{hash(link)}"
    except:
        return f"aw_{hash(link)}"

def scrape_anime_updated():
    print("Inizio scraping da AnimeWorld...")
    scraper = cloudscraper.create_scraper()
    
    try:
        response = scraper.get(UPDATED_URL)
        if response.status_code != 200:
            print("Errore connessione")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.select('.film-list .item')
        
        stremio_metas = []

        for item in items:
            try:
                # Titolo
                title_tag = item.select_one('.name')
                title = title_tag.get_text(strip=True) if title_tag else "Sconosciuto"
                
                # Episodio
                ep_tag = item.select_one('.ep')
                episode = ep_tag.get_text(strip=True) if ep_tag else ""
                
                # Link
                link_tag = item.select_one('a')
                url_path = link_tag['href'] if link_tag else ""
                
                # Immagine (Poster)
                img_tag = item.select_one('img')
                poster = img_tag['src'] if img_tag else ""
                
                # ID Univoco per Stremio
                stremio_id = get_id_from_link(url_path)

                # Creiamo l'oggetto Meta per Stremio
                meta = {
                    "id": stremio_id,
                    "type": "series",  # Anime sono solitamente serie
                    "name": title,
                    "poster": poster,
                    "description": f"Ultimo episodio: {episode}",
                    "posterShape": "poster"
                }
                
                stremio_metas.append(meta)

            except Exception as e:
                print(f"Errore parsing elemento: {e}")
                continue

        return stremio_metas

    except Exception as e:
        print(f"Errore critico: {e}")
        return []

def generate_stremio_files(metas):
    # 1. Configurazione del MANIFEST
    manifest = {
        "id": "community.animeworld.updated",
        "version": "1.0.0",
        "name": "AnimeWorld Updated",
        "description": "Gli ultimi episodi usciti su AnimeWorld",
        "resources": ["catalog", "meta"],
        "types": ["series", "movie"],
        "catalogs": [
            {
                "type": "series",
                "id": "animeworld_updated",
                "name": "AnimeWorld Novità",
                "extra": [{"name": "search", "isRequired": False}]
            }
        ],
        "idPrefixes": ["aw_"]
    }

    # 2. Salva il MANIFEST.JSON
    with open("manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
    print("✅ manifest.json generato.")

    # 3. Creazione struttura cartelle per il catalogo statico
    # Stremio cerca: /catalog/series/animeworld_updated.json
    output_dir = "catalog/series"
    os.makedirs(output_dir, exist_ok=True)

    catalog_data = {
        "metas": metas
    }

    # 4. Salva il CATALOGO
    with open(f"{output_dir}/animeworld_updated.json", "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, indent=4)
    print(f"✅ Catalogo salvato in {output_dir}/animeworld_updated.json")

if __name__ == "__main__":
    # Esegui scraping
    anime_data = scrape_anime_updated()
    
    if anime_data:
        print(f"Trovati {len(anime_data)} anime. Generazione file...")
        generate_stremio_files(anime_data)
    else:
        print("Nessun dato trovato.")