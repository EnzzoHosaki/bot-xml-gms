import json
import logging
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from config import settings

logger = logging.getLogger(__name__)

class BrowserHandler:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.driver: webdriver.Chrome = None

    def start_browser(self) -> webdriver.Chrome:
        logger.info(f"Iniciando o navegador em modo {'headless' if self.headless else 'com interface'}.")
        
        chrome_options = ChromeOptions()
        
        download_dir = str(settings.PENDING_DIR)
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.set_capability('goog:loggingPrefs', {
            'browser': 'ALL',
            'performance': 'ALL',
        })

        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        if self.headless:
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-gpu") 
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            chrome_options.add_argument('--log-level=3')

        try:
            configured_driver_path = settings.chrome_driver_path

            if configured_driver_path and Path(configured_driver_path).exists():
                logger.info(f"Usando ChromeDriver configurado em: {configured_driver_path}")
                service = ChromeService(executable_path=configured_driver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            elif Path("/usr/local/bin/chromedriver").exists():
                logger.info("Usando ChromeDriver padrão do container: /usr/local/bin/chromedriver")
                service = ChromeService(executable_path="/usr/local/bin/chromedriver")
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                logger.info("ChromeDriver não encontrado em caminho fixo. Usando Selenium Manager automático.")
                self.driver = webdriver.Chrome(options=chrome_options)

            # Configurar download via CDP (essencial para headless e mais confiável em geral)
            self.driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                "behavior": "allow",
                "downloadPath": download_dir
            })
            logger.info(f"Download configurado via CDP para: {download_dir}")

            # Habilitar domínio Network do CDP para capturar eventos de rede nos performance logs
            try:
                self.driver.execute_cdp_cmd("Network.enable", {})
                logger.debug("CDP Network domain habilitado.")
            except Exception as cdp_err:
                logger.debug(f"Não foi possível habilitar CDP Network domain: {cdp_err}")

            logger.info("Navegador iniciado com sucesso.")
            return self.driver
        
        except Exception as e:
            logger.error(f"Não foi possível iniciar o Chrome Driver: {e}", exc_info=True)
            return None

    def take_screenshot(self, name: str = "debug") -> str:
        """Captura screenshot para diagnóstico. Retorna o caminho do arquivo."""
        if not self.driver:
            logger.warning("Driver não disponível para capturar screenshot.")
            return None
        try:
            screenshots_dir = settings.BASE_DIR / "logs" / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = screenshots_dir / f"{name}_{timestamp}.png"
            self.driver.save_screenshot(str(filepath))
            logger.info(f"📸 Screenshot salva: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"Falha ao capturar screenshot: {e}")
            return None

    def get_browser_console_logs(self) -> list:
        """Returns and clears browser console log entries (one-time read)."""
        if not self.driver:
            return []
        try:
            return self.driver.get_log('browser')
        except Exception as e:
            logger.debug(f"Logs do console do browser indisponíveis: {e}")
            return []

    def get_performance_logs(self) -> list:
        """Returns and clears CDP performance log entries (one-time read)."""
        if not self.driver:
            return []
        try:
            return self.driver.get_log('performance')
        except Exception as e:
            logger.debug(f"Logs de performance indisponíveis: {e}")
            return []

    def log_browser_diagnostics(self, context: str = "") -> None:
        """Logs browser console errors/warnings and relevant CDP network events."""
        prefix = f"[{context}] " if context else ""

        browser_logs = self.get_browser_console_logs()
        if browser_logs:
            errors = [e for e in browser_logs if e.get('level') in ('SEVERE', 'WARNING')]
            if errors:
                for entry in errors:
                    logger.warning(f"{prefix}Console browser [{entry['level']}]: {entry.get('message', '')[:300]}")
            else:
                logger.debug(f"{prefix}Console browser: {len(browser_logs)} entradas, nenhum erro.")
        else:
            logger.debug(f"{prefix}Console browser: vazio.")

        perf_logs = self.get_performance_logs()
        dl_events = []
        for entry in perf_logs:
            try:
                msg = json.loads(entry.get('message', '{}'))
                method = msg.get('message', {}).get('method', '')
                if any(k in method for k in ['Download', 'Page.download', 'Network.responseReceived']):
                    params = msg.get('message', {}).get('params', {})
                    dl_events.append(f"{method}: {str(params)[:200]}")
            except Exception:
                continue
        if dl_events:
            for ev in dl_events:
                logger.info(f"{prefix}Evento CDP: {ev}")
        else:
            logger.debug(f"{prefix}Nenhum evento de download/resposta nos performance logs.")

    def close_browser(self):
        if self.driver:
            logger.info("Fechando o navegador.")
            self.driver.quit()
            self.driver = None