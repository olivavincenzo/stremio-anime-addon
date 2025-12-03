import cloudscraper
from bs4 import BeautifulSoup
import json
import re
import os
import time

# Configurazione URL base
BASE_URL = "https://www.animeworld.ac"
UPDATED_URL = f"{BASE_URL}/updated"

def get_id_from_link(link):
    """
    Estrae l'ID univoco dal link di AnimeWorld.
    Esempio: /play/nome-anime.1234/ep-1 -> aw_1234
    """
    try:
        match = re.search(r'\.([a-zA-Z0-9]+)/', link)
        if match:
            return f"aw_{match.group(1)}"
        return f"aw_{hash(link)}"
    except:
        return f"aw_{hash(link)}"

def scrape_anime_updated():
    print("Inizio scraping da AnimeWorld...")
    scraper = cloudscraper.create_scraper()
    
    try:
        response = scraper.get(UPDATED_URL)
        if response.status_code != 200:
            print(f"Errore connessione: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.select('.film-list .item')
        
        stremio_metas = []

        for item in items:
            try:
                # Dati base
                title_tag = item.select_one('.name')
                title = title_tag.get_text(strip=True) if title_tag else "Sconosciuto"
                
                ep_tag = item.select_one('.ep')
                episode = ep_tag.get_text(strip=True) if ep_tag else ""
                
                link_tag = item.select_one('a')
                url_path = link_tag['href'] if link_tag else ""
                
                img_tag = item.select_one('img')
                poster = img_tag['src'] if img_tag else ""
                
                stremio_id = get_id_from_link(url_path)

                # Creiamo l'oggetto Meta
                # Nota: Per un addon statico veloce, usiamo gli stessi dati per preview e dettagli.
                # Per avere descrizioni lunghe bisognerebbe entrare in ogni link (lento).
                meta = {
                    "id": stremio_id,
                    "type": "series",
                    "name": title,
                    "poster": poster,
                    "description": f"Ultimo episodio rilasciato: {episode}.\n\nDisponibile su AnimeWorld.",
                    "posterShape": "poster",
                    # Aggiungiamo un background generico o lo stesso poster se manca
                    "background": poster 
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
    # 1. Genera MANIFEST.JSON
    manifest = {
        "id": "community.animeworld.updated",
        "version": "1.0.1",
        "name": "AnimeWorld Updated",
        "description": "Gli ultimi episodi usciti su AnimeWorld",
        "resources": ["catalog", "meta"], # 'meta' è fondamentale qui
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

    with open("manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
    print("✅ manifest.json generato.")

    # 2. Genera CATALOGO
    # Percorso: catalog/series/animeworld_updated.json
    cat_dir = "catalog/series"
    os.makedirs(cat_dir, exist_ok=True)

    catalog_data = {"metas": metas} # Nel catalogo mettiamo la lista completa

    with open(f"{cat_dir}/animeworld_updated.json", "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, indent=4)
    print(f"✅ Catalogo salvato in {cat_dir}/animeworld_updated.json")

    # 3. Genera META (Dettagli per ogni singolo anime)
    # Percorso: meta/series/ID.json
    meta_dir = "meta/series"
    os.makedirs(meta_dir, exist_ok=True)

    print(f"Generazione {len(metas)} file di metadati individuali...")
    
    for meta in metas:
        # Stremio si aspetta un oggetto con chiave "meta" che contiene i dettagli
        meta_file_content = {"meta": meta}
        
        file_name = f"{meta['id']}.json"
        file_path = os.path.join(meta_dir, file_name)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(meta_file_content, f, indent=4)
            
    print(f"✅ File metadati salvati in {meta_dir}/")

if __name__ == "__main__":
    anime_data = scrape_anime_updated()
    
    if anime_data:
        print(f"Trovati {len(anime_data)} anime. Inizio generazione file...")
        generate_stremio_files(anime_data)
    else:
        print("Nessun dato trovato.")