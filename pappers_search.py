import scrapy
from scrapy.crawler import CrawlerProcess
import re

class EntrepriseSpider(scrapy.Spider):
    name = 'entreprise_spider'
    
    def __init__(self, url=None, *args, **kwargs):
        super(EntrepriseSpider, self).__init__(*args, **kwargs)
        self.start_urls = [url] if url else []
    
    def parse(self, response):
        """
        Extrait les informations détaillées d'une entreprise à partir d'une page HTML
        """
        # Informations générales
        nom_entreprise = response.css('h1.big-text::text').get()
        if nom_entreprise:
            nom_entreprise = nom_entreprise.strip()
        
        # Extraire le SIREN (en utilisant l'attribut id)
        siren = response.css('a#siren-copyable::text').get()
        if siren:
            siren = siren.strip()
            # Nettoyer le SIREN (enlever les espaces)
            siren = re.sub(r'\s+', '', siren)
        
        # Statut
        statut = response.css('span.status span::text').get()
        if statut:
            statut = statut.strip()
        
        # Informations principales dans la table du résumé
        adresse = response.xpath('//th[contains(text(), "Adresse")]/following-sibling::td/text()').get()
        if adresse:
            adresse = adresse.strip()
        
        activite = response.xpath('//th[contains(text(), "Activité")]/following-sibling::td/text()').get()
        if activite:
            activite = activite.strip()
        
        effectif = response.xpath('//th[contains(text(), "Effectif")]/following-sibling::td/text()').get()
        if effectif:
            effectif = effectif.strip()
        
        date_creation = response.xpath('//th[contains(text(), "Création")]/following-sibling::td/text()').get()
        if date_creation:
            date_creation = date_creation.strip()
        
        dirigeant = response.xpath('//th[contains(text(), "Dirigeant")]/following-sibling::td//a/text()').get()
        if dirigeant:
            dirigeant = dirigeant.strip()
        
        # Informations juridiques
        siret = response.xpath('//th[contains(text(), "SIRET")]/following-sibling::td/text()').get()
        if siret:
            siret = siret.strip()
            # Nettoyer le SIRET (enlever les espaces)
            siret = re.sub(r'\s+', '', siret)
        
        forme_juridique = response.xpath('//th[contains(text(), "Forme juridique")]/following-sibling::td/text()').get()
        if forme_juridique:
            forme_juridique = forme_juridique.strip()
        
        tva = response.xpath('//th[contains(text(), "Numéro de TVA")]/following-sibling::td//span/text()').get()
        if tva:
            tva = tva.strip()
        
        capital_social = response.xpath('//th[contains(text(), "Capital social")]/following-sibling::td/text()').get()
        if capital_social:
            capital_social = capital_social.strip()
        
        # Activité détaillée
        activite_principale = response.xpath('//th[contains(text(), "Activité principale déclarée")]/following-sibling::td//span/text()').get()
        if activite_principale:
            activite_principale = activite_principale.strip()
        
        code_naf = response.xpath('//th[contains(text(), "Code NAF ou APE")]/following-sibling::td/span/text()').get()
        if code_naf:
            code_naf = code_naf.strip().split(' ')[0]
        
        domaine_activite = response.xpath('//th[contains(text(), "Domaine d\'activité")]/following-sibling::td/text()').get()
        if domaine_activite:
            domaine_activite = domaine_activite.strip()
        
        # Informations de mise à jour
        dates_maj = response.css('div.date-maj span::text').getall()
        date_maj_rcs = None
        date_maj_rne = None
        date_maj_insee = None
        
        if dates_maj and len(dates_maj) >= 3:
            # Extraction des dates avec regex
            for date_text in dates_maj:
                if "RCS" in date_text:
                    match = re.search(r'le (\d{2}/\d{2}/\d{4})', date_text)
                    if match:
                        date_maj_rcs = match.group(1)
                elif "RNE" in date_text:
                    match = re.search(r'le (\d{2}/\d{2}/\d{4})', date_text)
                    if match:
                        date_maj_rne = match.group(1)
                elif "INSEE" in date_text:
                    match = re.search(r'le (\d{2}/\d{2}/\d{4})', date_text)
                    if match:
                        date_maj_insee = match.group(1)
        
        # Date de clôture
        date_cloture = response.xpath('//th[contains(text(), "Date de clôture d\'exercice comptable")]/following-sibling::td/text()').get()
        if date_cloture:
            date_cloture = date_cloture.strip()
        
        # Retourner toutes les informations extraites
        return {
            'nom': nom_entreprise,
            'siren': siren,
            'statut': statut,
            'adresse': adresse,
            'activite': activite,
            'effectif': effectif,
            'date_creation': date_creation,
            'dirigeant': dirigeant,
            'siret': siret,
            'forme_juridique': forme_juridique,
            'tva': tva,
            'capital_social': capital_social,
            'activite_principale': activite_principale,
            'code_naf': code_naf,
            'domaine_activite': domaine_activite,
            'date_maj_rcs': date_maj_rcs,
            'date_maj_rne': date_maj_rne,
            'date_maj_insee': date_maj_insee,
            'date_cloture': date_cloture,
        }


class HTMLContentSpider(scrapy.Spider):
    """
    Spider spécifique pour extraire les données d'une entreprise à partir de HTML brut
    au lieu d'une URL
    """
    name = 'html_content_spider'
    
    def __init__(self, html_content, *args, **kwargs):
        super(HTMLContentSpider, self).__init__(*args, **kwargs)
        self.html_content = html_content
        self.start_urls = ['file:///dummy']  # URL fictive qui sera remplacée
    
    def start_requests(self):
        # Au lieu de faire une requête HTTP, on utilise le HTML fourni directement
        yield scrapy.Request(
            url='file:///dummy',  # URL fictive
            callback=self.parse,
            dont_filter=True,
            meta={'html_content': self.html_content}
        )
    
    def parse(self, response):
        # On utilise le même parseur que EntrepriseSpider
        # mais on prend le HTML depuis meta
        html_content = response.meta.get('html_content')
        if not html_content:
            self.logger.error("Pas de contenu HTML fourni")
            return {}
        
        # Créer une réponse à partir du HTML
        response = scrapy.http.HtmlResponse(
            url='file:///dummy',
            body=html_content.encode('utf-8')
        )
        
        # Utiliser le même code de parsing que EntrepriseSpider
        nom_entreprise = response.css('h1.big-text::text').get()
        if nom_entreprise:
            nom_entreprise = nom_entreprise.strip()
        
        # Extraire le SIREN
        siren = response.css('a#siren-copyable::text').get()
        if siren:
            siren = siren.strip()
            siren = re.sub(r'\s+', '', siren)
        
        # Statut
        statut = response.css('span.status span::text').get()
        if statut:
            statut = statut.strip()
        
        # Informations principales dans la table du résumé
        adresse = response.xpath('//th[contains(text(), "Adresse")]/following-sibling::td/text()').get()
        if adresse:
            adresse = adresse.strip()
        
        activite = response.xpath('//th[contains(text(), "Activité")]/following-sibling::td/text()').get()
        if activite:
            activite = activite.strip()
        
        effectif = response.xpath('//th[contains(text(), "Effectif")]/following-sibling::td/text()').get()
        if effectif:
            effectif = effectif.strip()
        
        date_creation = response.xpath('//th[contains(text(), "Création")]/following-sibling::td/text()').get()
        if date_creation:
            date_creation = date_creation.strip()
        
        dirigeant = response.xpath('//th[contains(text(), "Dirigeant")]/following-sibling::td//a/text()').get()
        if dirigeant:
            dirigeant = dirigeant.strip()
        
        # Informations juridiques
        siret = response.xpath('//th[contains(text(), "SIRET")]/following-sibling::td/text()').get()
        if siret:
            siret = siret.strip()
            siret = re.sub(r'\s+', '', siret)
        
        forme_juridique = response.xpath('//th[contains(text(), "Forme juridique")]/following-sibling::td/text()').get()
        if forme_juridique:
            forme_juridique = forme_juridique.strip()
        
        tva = response.xpath('//th[contains(text(), "Numéro de TVA")]/following-sibling::td//span/text()').get()
        if tva:
            tva = tva.strip()
        
        capital_social = response.xpath('//th[contains(text(), "Capital social")]/following-sibling::td/text()').get()
        if capital_social:
            capital_social = capital_social.strip()
        
        # Activité détaillée
        activite_principale = response.xpath('//th[contains(text(), "Activité principale déclarée")]/following-sibling::td//span/text()').get()
        if activite_principale:
            activite_principale = activite_principale.strip()
        
        code_naf = response.xpath('//th[contains(text(), "Code NAF ou APE")]/following-sibling::td/span/text()').get()
        if code_naf:
            code_naf = code_naf.strip().split(' ')[0]
        
        domaine_activite = response.xpath('//th[contains(text(), "Domaine d\'activité")]/following-sibling::td/text()').get()
        if domaine_activite:
            domaine_activite = domaine_activite.strip()
        
        # Informations de mise à jour
        dates_maj = response.css('div.date-maj span::text').getall()
        date_maj_rcs = None
        date_maj_rne = None
        date_maj_insee = None
        
        if dates_maj and len(dates_maj) >= 3:
            # Extraction des dates avec regex
            for date_text in dates_maj:
                if "RCS" in date_text:
                    match = re.search(r'le (\d{2}/\d{2}/\d{4})', date_text)
                    if match:
                        date_maj_rcs = match.group(1)
                elif "RNE" in date_text:
                    match = re.search(r'le (\d{2}/\d{2}/\d{4})', date_text)
                    if match:
                        date_maj_rne = match.group(1)
                elif "INSEE" in date_text:
                    match = re.search(r'le (\d{2}/\d{2}/\d{4})', date_text)
                    if match:
                        date_maj_insee = match.group(1)
        
        # Date de clôture
        date_cloture = response.xpath('//th[contains(text(), "Date de clôture d\'exercice comptable")]/following-sibling::td/text()').get()
        if date_cloture:
            date_cloture = date_cloture.strip()
        
        # Retourner toutes les informations extraites
        return {
            'nom': nom_entreprise,
            'siren': siren,
            'statut': statut,
            'adresse': adresse,
            'activite': activite,
            'effectif': effectif,
            'date_creation': date_creation,
            'dirigeant': dirigeant,
            'siret': siret,
            'forme_juridique': forme_juridique,
            'tva': tva,
            'capital_social': capital_social,
            'activite_principale': activite_principale,
            'code_naf': code_naf,
            'domaine_activite': domaine_activite,
            'date_maj_rcs': date_maj_rcs,
            'date_maj_rne': date_maj_rne,
            'date_maj_insee': date_maj_insee,
            'date_cloture': date_cloture,
        }


# Fonction utilitaire pour extraire les données d'une page web
def scrape_entreprise_from_url(url, output_file=None):
    """
    Scrape les informations d'une entreprise à partir d'une URL
    
    Args:
        url: URL de la page d'entreprise à scraper
        output_file: Fichier de sortie pour les données (facultatif)
    
    Returns:
        Dictionnaire des données extraites
    """
    settings = {
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'LOG_LEVEL': 'ERROR',
    }
    
    if output_file:
        settings.update({
            'FEED_FORMAT': 'json',
            'FEED_URI': output_file,
        })
    
    process = CrawlerProcess(settings)
    process.crawl(EntrepriseSpider, url=url)
    process.start()  # Le processus se bloque ici jusqu'à la fin du crawling


# Fonction utilitaire pour extraire les données à partir d'un contenu HTML
def scrape_entreprise_from_html(html_content):
    """
    Scrape les informations d'une entreprise à partir du contenu HTML brut
    
    Args:
        html_content: Contenu HTML à parser
    
    Returns:
        Dictionnaire des données extraites
    """
    settings = {
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'LOG_LEVEL': 'ERROR',
    }
    
    # Utiliser CrawlerRunner au lieu de CrawlerProcess pour éviter de bloquer le thread
    from scrapy.crawler import CrawlerRunner
    from twisted.internet import reactor
    import threading
    from scrapy.utils.project import get_project_settings
    
    runner = CrawlerRunner(settings)
    
    # Deferred qui sera résolu lorsque le crawling sera terminé
    from twisted.internet.defer import Deferred
    results = []
    d = Deferred()
    
    # Modifier le SpiderLoader pour accepter notre spider personnalisé
    class CustomSpider(HTMLContentSpider):
        def parse(self, response):
            result = super().parse(response)
            results.append(result)
            return result
    
    # Exécuter le spider
    d = runner.crawl(CustomSpider, html_content=html_content)
    d.addBoth(lambda _: reactor.stop())
    
    # Exécuter le réacteur dans un thread séparé
    threading.Thread(target=reactor.run, args=(False,)).start()
    
    # Attendre que le réacteur s'arrête
    while reactor.running:
        pass
    
    return results[0] if results else {}


# Si le script est exécuté directement
if __name__ == "__main__":
    import sys
    url = "https://annuaire-entreprises.data.gouv.fr/entreprise/"
    siren= "928364009"
    if len(sys.argv) > 1:
        url = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else 'entreprise_data.json'
        print(f"Scraping de l'URL: {url} vers {output_file}")
        scrape_entreprise_from_url(url, output_file)
    else:
        print("Usage: python scraper.py <url> [output_file]")