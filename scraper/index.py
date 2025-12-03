import cloudscraper
from bs4 import BeautifulSoup
import json
import os

def get_latest_episodes():
    url = "https://www.animeworld.ac/"
    
    scraper = cloudscraper.create_scraper()
    
    try:
        response = scraper.get(url)
        
        if response.status_code != 200:
            print(f"Errore di connessione: {response.status_code}")
            return []

        # --- MODIFICA: SALVATAGGIO DEL FILE HTML ---
        # Salviamo il contenuto grezzo (response.text) in un file chiamato "animeworld.html"
        with open("animeworld.html", "w", encoding="utf-8") as file:
            file.write(response.text)
        print("Pagina HTML salvata correttamente nel file 'animeworld.html'")
        # -------------------------------------------

        soup = BeautifulSoup(response.text, 'html.parser')
        
        anime_list = []
        items = soup.select('.film-list .item')
        
        for item in items:
            try:
                title_tag = item.select_one('.name')
                link_tag = item.select_one('a')
                episode_tag = item.select_one('.ep')
                img_tag = item.select_one('img')
                
                if title_tag and link_tag:
                    title = title_tag.get_text(strip=True)
                    episode = episode_tag.get_text(strip=True) if episode_tag else "N/A"
                    relative_url = link_tag['href']
                    
                    # Extract ID from URL
                    # Example: /play/anime-name.id/episode-id -> anime-name.id
                    parts = relative_url.strip('/').split('/')
                    if len(parts) >= 2:
                        slug_id = parts[-2]
                    else:
                        slug_id = parts[-1] # Fallback if structure is different
                    
                    stremio_id = f"aw:{slug_id}"
                    
                    # Extract Poster
                    poster = img_tag['src'] if img_tag else ""
                    if poster and not poster.startswith('http'):
                        poster = "https:" + poster if poster.startswith('//') else "https://www.animeworld.ac" + poster

                    data = {
                        "id": stremio_id,
                        "type": "series",
                        "name": title,
                        "poster": poster,
                        "description": f"Latest episode: {episode}",
                        "genres": ["Anime"]
                    }
                    anime_list.append(data)
            except AttributeError:
                continue
                
        return anime_list

    except Exception as e:
        print(f"Si è verificato un errore: {e}")
        return []

def save_to_catalog(anime_list):
    # Path to catalog/anime/latest.json relative to this script
    catalog_path = os.path.join(os.path.dirname(__file__), '../catalog/anime/latest.json')
    catalog_path = os.path.abspath(catalog_path)
    
    data = {"metas": anime_list}
    
    try:
        with open(catalog_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Catalogo aggiornato: {catalog_path}")
    except Exception as e:
        print(f"Errore durante il salvataggio del catalogo: {e}")

# Esecuzione
ultimi = get_latest_episodes()

if ultimi:
    save_to_catalog(ultimi)
    print(f"\n--- Aggiornati {len(ultimi)} anime nel catalogo ---")
    for anime in ultimi:
        print(f"[{anime['description']}] {anime['name']}")
else:
    print("Nessun anime trovato o errore durante lo scraping.")