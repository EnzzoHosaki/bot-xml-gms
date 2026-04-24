#page_objects/export_page.py
import time
import logging
from pathlib import Path
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from .base_page import BasePage
from config import settings
from src.utils.exceptions import NoInvoicesFoundException

logger = logging.getLogger(__name__)

class ExportPage(BasePage):
    def __init__(self, driver: WebDriver, selectors: dict):
        super().__init__(driver)
        self.selectors = selectors

    def export_data(self, document_type: str, emitter: str, operation_type: str, file_type: str, invoice_situation: str, start_date: str, end_date: str, stores_to_process: list):
        try:
            with self.switch_to_iframe(self.selectors['legado_frame']):
                self.click(self.selectors['include_button'])
              
                with self.switch_to_iframe(self.selectors['popup_frame']):
                    logger.info("Entrou no iframe do popup.")

                    self.select_option_by_value(self.selectors['document_type_dropdown'], document_type)

                    self.click(self.selectors['start_date_input'])
                    self.add_text_to_field(self.selectors['start_date_input'], start_date)
                    self.click(self.selectors['end_date_input'])
                    self.press_key(self.selectors['end_date_input'], 'HOME')
                    self.add_text_to_field(self.selectors['end_date_input'], end_date)

                    self.select_option_by_value(self.selectors['emitter_dropdown'], emitter)
                    if operation_type != 'TODAS':
                        self.select_option_by_value(self.selectors['operation_type_dropdown'], operation_type)
                    self.select_option_by_value(self.selectors['file_type_dropdown'], file_type)
                    self.select_option_by_value(self.selectors['invoice_situation_dropdown'], invoice_situation)

                    if stores_to_process:
                        logger.info(f"Selecionando as lojas via input: {stores_to_process}")
                        
                        for store_code in stores_to_process:
                            try:
                                self.send_keys(self.selectors['stores_input'], str(store_code))
                                option_selector = f"//li[@role='option' and contains(., '{store_code}')]"
                                _by = self._get_by(option_selector)
                                # O dropdown re-renderiza após cada seleção; retry protege contra StaleElementReference
                                for _attempt in range(3):
                                    try:
                                        el = WebDriverWait(self.driver, settings.DEFAULT_TIMEOUT).until(
                                            EC.element_to_be_clickable((_by, option_selector))
                                        )
                                        el.click()
                                        break
                                    except StaleElementReferenceException:
                                        if _attempt == 2:
                                            raise
                                logger.info(f"Loja '{store_code}' selecionada com sucesso.")

                            except Exception as e:
                                logger.error(f"Não foi possível selecionar a loja '{store_code}': {e}")
                                raise

                    self.wait_for_element(self.selectors['export_button'])
                    self.click( self.selectors['popup_header'])
                    self.click(self.selectors['export_button'])
                    logger.info("Clique no botão de exportar realizado.")
                    if self.is_element_present(self.selectors['alert_msg'], timeout=settings.DEFAULT_TIMEOUT // 10):
                        alert_element = self._find_element(self.selectors['alert_msg'])
                        if "Não existem notas a serem exportadas para esse filtro." in alert_element.text:
                            logger.warning("Nenhuma nota encontrada para os filtros especificados. Encerrando o processo de exportação.")
                            raise NoInvoicesFoundException("Não existem notas a serem exportadas para o filtro selecionado.")

                    logger.info("Interação no popup concluída.")
                    
            logger.info("Processo de exportação dentro do iframe concluído.")

        except KeyError as e:
            logger.error(f"Seletor não encontrado no dicionário de exportação: {e}")
            raise
        except Exception as e:
            logger.error(f"Ocorreu um erro durante a exportação: {e}")
            raise

    def wait_for_export_completion(self):
        logger.info("Iniciando monitoramento da tabela de exportação (verificando apenas a primeira linha)...")
        minutes = 180
        timeout = time.time() + 60 * minutes
        
        while time.time() < timeout:
            try:
                with self.switch_to_iframe(self.selectors['legado_frame']):
                    logger.info("Analisando a primeira linha da tabela de exportação...")
                    
                    first_row_selector = f"({self.selectors['table_rows']})[3]"
                    
                    if not self.is_element_present(first_row_selector):
                        logger.info("Nenhuma linha encontrada na tabela ainda. Aguardando...")
                    else:
                        first_row_element = self.wait_for_element(first_row_selector)
                        columns = self.find_child_elements(first_row_element, "td")
                        status_col = columns[18].text
                        logger.info(f"Status atual da exportação: '{status_col}'")

                        if "Concluído" in status_col:
                            logger.info("✅ Exportação concluída com sucesso!")
                            
                            # Capturar screenshot do estado "Concluído" para diagnóstico
                            try:
                                self.driver.switch_to.default_content()
                                screenshots_dir = settings.BASE_DIR / "logs" / "screenshots"
                                screenshots_dir.mkdir(parents=True, exist_ok=True)
                                screenshot_path = screenshots_dir / f"export_concluded_{int(time.time())}.png"
                                self.driver.save_screenshot(str(screenshot_path))
                                logger.info(f"📸 Screenshot do status concluído: {screenshot_path}")
                            except Exception:
                                pass
                            
                            return
                        if "Em processamento" in status_col:
                            logger.info("⏳ A exportação está em processamento. Continuando a monitorar...")
                        if "Pendente" in status_col:
                            logger.info("⏳ A exportação está pendente. Continuando a monitorar...")
                        if "com Erro" in status_col:
                            logger.error("❌ A exportação falhou, status 'Com erro' encontrado na tabela.")
                            raise Exception("A exportação retornou o status 'Com erro'.")

            except Exception as e:
                logger.error(f"Ocorreu um erro inesperado durante o monitoramento: {e}")
                raise

            logger.info("Aguardando 30 segundos antes de verificar a tabela novamente...")
            time.sleep(30)
            self.driver.refresh()
            with self.switch_to_iframe(self.selectors['legado_frame']):
                self.wait_for_element(self.selectors['search_button'])
                self.click(self.selectors['search_button'])
                _row_sel = f"({self.selectors['table_rows']})[3]"
                _by = self._get_by(_row_sel)
                try:
                    WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((_by, _row_sel)))
                except TimeoutException:
                    pass  # Tabela pode estar vazia, o loop externo verificará
                
        raise TimeoutError(f"A exportação não foi concluída no tempo limite de {minutes} minutos.")
    
    def download_exports(self):
        logger.info("Iniciando o download dos arquivos exportados...")
        pending_dir = settings.PENDING_DIR

        # Remover resíduos de downloads incompletos de execuções anteriores.
        stale_temp_files = [f for f in pending_dir.glob('*') if f.suffix in ('.crdownload', '.part', '.tmp')]
        if stale_temp_files:
            for temp_file in stale_temp_files:
                try:
                    temp_file.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Não foi possível remover arquivo temporário antigo '{temp_file.name}': {e}")
            logger.info(f"Arquivos temporários antigos removidos: {[f.name for f in stale_temp_files]}")

        # Limpar arquivos antigos do diretório pending antes de iniciar o download
        existing_files_before = set(pending_dir.glob('*'))
        logger.info(f"Arquivos existentes em pending antes do download: {[f.name for f in existing_files_before]}")

        try:
            with self.switch_to_iframe(self.selectors['legado_frame']):
                first_row_selector = f"({self.selectors['table_rows']})[3]"
                self.wait_for_element(first_row_selector)
                
                # Clicar na linha para selecioná-la
                logger.info("Clicando na primeira linha da tabela para selecioná-la...")
                self.click(first_row_selector)
                _by = self._get_by(first_row_selector)
                WebDriverWait(self.driver, 3).until(EC.presence_of_element_located((_by, first_row_selector)))

                # Verificar se a linha foi selecionada (class 'selected' ou similar)
                first_row_element = self._find_element(first_row_selector)
                row_classes = first_row_element.get_attribute("class") or ""
                logger.info(f"Classes da linha após clique: '{row_classes}'")

                # Tentar também clicar no checkbox/input da linha se existir
                try:
                    checkbox_selector = f"({self.selectors['table_rows']})[3]//input[@type='checkbox']"
                    if self.is_element_present(checkbox_selector, timeout=2):
                        self.click(checkbox_selector)
                        logger.info("Checkbox da linha clicado.")
                        _cb_by = self._get_by(checkbox_selector)
                        try:
                            WebDriverWait(self.driver, 2).until(EC.element_to_be_clickable((_cb_by, checkbox_selector)))
                        except TimeoutException:
                            pass
                except Exception:
                    logger.debug("Nenhum checkbox encontrado na linha (pode não ser necessário).")

                download_button_selector = self.selectors['download_button']
                self.wait_for_element(download_button_selector)
                
                # Log do estado do botão de download antes de clicar
                download_btn = self._find_element(download_button_selector)
                btn_enabled = download_btn.is_enabled()
                btn_displayed = download_btn.is_displayed()
                logger.info(f"Botão de download - Enabled: {btn_enabled}, Displayed: {btn_displayed}")

                if not btn_enabled:
                    logger.warning("⚠️ O botão de download está desabilitado! A linha pode não estar selecionada corretamente.")
                
                # Tentar click normal primeiro
                self.click(download_button_selector)
                logger.info("Clique no botão de download realizado.")

                # Aguardar possível alert do browser com WebDriverWait
                try:
                    WebDriverWait(self.driver, 3).until(EC.alert_is_present())
                    alert = self.driver.switch_to.alert
                    alert_text = alert.text
                    logger.info(f"Alert detectado após click no download: '{alert_text}'")
                    alert.accept()
                    logger.info("Alert aceito.")
                except TimeoutException:
                    logger.debug("Nenhum alert do browser detectado após click no download.")

        except Exception as e:
            logger.error(f"Ocorreu um erro durante o processo de download: {e}")
            # Capturar screenshot para diagnóstico
            try:
                self.driver.switch_to.default_content()
                screenshots_dir = settings.BASE_DIR / "logs" / "screenshots"
                screenshots_dir.mkdir(parents=True, exist_ok=True)
                screenshot_path = screenshots_dir / f"download_error_{int(time.time())}.png"
                self.driver.save_screenshot(str(screenshot_path))
                logger.info(f"📸 Screenshot de erro salva: {screenshot_path}")
            except Exception as ss_err:
                logger.debug(f"Falha ao salvar screenshot de erro: {ss_err}")
            raise

        # AGUARDAR O DOWNLOAD SER CONCLUÍDO (fora do iframe)
        logger.info("Aguardando o download do arquivo ser concluído no diretório pending...")
        self._wait_for_download_complete(pending_dir, existing_files_before)
        logger.info("✅ Download dos arquivos concluído com sucesso.")

    def _wait_for_download_complete(self, pending_dir: Path, files_before: set, timeout_seconds: int = None):
        """Aguarda o download do arquivo ser concluído no diretório pending."""
        if timeout_seconds is None:
            timeout_seconds = settings.download_timeout

        logger.info(f"Monitorando diretório de downloads por até {timeout_seconds} segundos...")
        start_time = time.time()
        download_detected = False
        no_temp_files_since = None

        # Snapshot inicial por nome para detectar sobrescrita de arquivo existente.
        initial_snapshot = {}
        for file_path in files_before:
            try:
                stat = file_path.stat()
                initial_snapshot[file_path.name] = {
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "is_dir": file_path.is_dir(),
                }
            except FileNotFoundError:
                continue

        # Controle de estabilidade para evitar considerar arquivo ainda em escrita como concluído.
        candidate_stability = {}

        while time.time() - start_time < timeout_seconds:
            current_files = list(pending_dir.glob('*'))

            temp_files = [f for f in current_files if f.suffix in ('.crdownload', '.part', '.tmp')]
            non_temp_files = [f for f in current_files if f not in temp_files]

            changed_or_new_files = []
            candidate_artifacts = []

            for f in non_temp_files:
                try:
                    stat = f.stat()
                except FileNotFoundError:
                    continue

                current_meta = {
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "is_dir": f.is_dir(),
                }

                baseline_meta = initial_snapshot.get(f.name)
                is_new = baseline_meta is None
                is_changed = baseline_meta is not None and current_meta != baseline_meta

                if is_new or is_changed:
                    changed_or_new_files.append(f)
                    if f.suffix == '.zip' or f.is_dir():
                        candidate_artifacts.append((f, current_meta))

            if temp_files:
                if not download_detected:
                    logger.info(f"📥 Download detectado! Arquivo(s) em progresso: {[f.name for f in temp_files]}")
                    download_detected = True
                else:
                    sizes = {f.name: f.stat().st_size for f in temp_files if f.exists()}
                    logger.debug(f"Download em progresso... Tamanhos: {sizes}")
                no_temp_files_since = None

            if changed_or_new_files and not download_detected:
                logger.info(f"📥 Atividade de download detectada por arquivos novos/atualizados: {[f.name for f in changed_or_new_files]}")
                download_detected = True

            if download_detected and not temp_files and no_temp_files_since is None:
                no_temp_files_since = time.time()

            if download_detected and candidate_artifacts:
                for candidate_file, current_meta in candidate_artifacts:
                    previous_meta = candidate_stability.get(candidate_file.name)
                    previous_base_meta = None
                    if previous_meta:
                        previous_base_meta = {
                            "size": previous_meta.get("size"),
                            "mtime": previous_meta.get("mtime"),
                            "is_dir": previous_meta.get("is_dir"),
                        }

                    if previous_base_meta == current_meta:
                        candidate_stability[candidate_file.name] = {
                            **current_meta,
                            "stable_hits": candidate_stability[candidate_file.name].get("stable_hits", 1) + 1,
                        }
                    else:
                        candidate_stability[candidate_file.name] = {
                            **current_meta,
                            "stable_hits": 1,
                        }

                stable_candidates = [
                    name for name, meta in candidate_stability.items()
                    if meta.get("stable_hits", 0) >= 2 and meta.get("size", 0) > 0
                ]

                if stable_candidates and no_temp_files_since and (time.time() - no_temp_files_since) >= 6:
                    logger.info(f"✅ Download concluído. Artefatos estáveis detectados: {stable_candidates}")
                    return

            if download_detected and not temp_files and not candidate_artifacts:
                logger.debug("Downloads temporários finalizaram, aguardando estabilização de artefatos finais...")

            elapsed = int(time.time() - start_time)
            if elapsed > 0 and elapsed % 30 == 0:
                logger.info(f"⏳ Aguardando download... ({elapsed}s decorridos)")

            time.sleep(3)

        # Timeout - capturar estado final para diagnóstico
        final_files = list(pending_dir.glob('*'))
        logger.error(f"❌ Timeout no download! Arquivos em pending após {timeout_seconds}s: {[f.name for f in final_files]}")
        
        # Capturar screenshot final
        try:
            self.driver.switch_to.default_content()
            screenshots_dir = settings.BASE_DIR / "logs" / "screenshots" 
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = screenshots_dir / f"download_timeout_{int(time.time())}.png"
            self.driver.save_screenshot(str(screenshot_path))
            logger.info(f"📸 Screenshot de timeout salva: {screenshot_path}")
        except Exception:
            pass

        raise TimeoutError(f"O download não foi concluído no tempo limite de {timeout_seconds} segundos.")
    
