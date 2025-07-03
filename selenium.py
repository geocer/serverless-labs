from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def list_office365_form_fields_with_proxy(url, proxy_address=None, proxy_port=None, proxy_username=None, proxy_password=None):
    """
    Navega até uma URL (idealmente uma página de login do Office 365) usando um proxy,
    e tenta listar os campos do formulário, considerando iFrames e carregamento dinâmico.

    Args:
        url (str): A URL da página web a ser inspecionada (ex: uma URL de login do Office 365).
        proxy_address (str, optional): O endereço IP ou hostname do servidor proxy. Ex: "192.168.1.1".
        proxy_port (int, optional): A porta do servidor proxy. Ex: 8080.
        proxy_username (str, optional): Nome de usuário para autenticação do proxy (se necessário).
        proxy_password (str, optional): Senha para autenticação do proxy (se necessário).
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Executa em modo headless (sem abrir o navegador visualmente)
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # --- Configuração do Proxy ---
    if proxy_address and proxy_port:
        proxy_string = f"{proxy_address}:{proxy_port}"
        print(f"Configurando proxy para: {proxy_string}")
        options.add_argument(f'--proxy-server={proxy_string}')

        if proxy_username and proxy_password:
            # Para proxies que exigem autenticação, é um pouco mais complexo e pode exigir
            # a extensão Selenium Wire ou um perfil de usuário do Chrome com as credenciais já salvas.
            # No entanto, podemos tentar uma abordagem comum que funciona para muitos.
            # NOTA: O método mais robusto para proxy com autenticação é via Selenium Wire.
            # Para este exemplo, vamos manter a simplicidade com as opções do Chrome,
            # que funcionam para proxies sem autenticação ou com autenticação via PAC/browser profile.
            print("Atenção: A autenticação de proxy via --proxy-server não é diretamente suportada para credenciais.")
            print("Considere usar Selenium Wire ou um perfil de usuário pré-configurado para autenticação robusta.")
            # Uma alternativa mais robusta para proxy com autenticação é usar "selenium-wire":
            # from seleniumwire import webdriver as webdriver_wire
            # driver = webdriver_wire.Chrome(...)
            # driver.proxy = {
            #     'http': f'http://{proxy_username}:{proxy_password}@{proxy_address}:{proxy_port}',
            #     'https': f'https://{proxy_username}:{proxy_password}@{proxy_address}:{proxy_port}'
            # }
            # Para o escopo deste script, vamos manter o webdriver padrão do Selenium.

    driver = None
    try:
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        print(f"Acessando a URL: {url}")
        driver.get(url)

        print("Esperando a página carregar...")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)

        print("Verificando a presença de iFrames...")
        iframes = driver.find_elements(By.TAG_NAME, "iframe")

        if iframes:
            print(f"Encontrado(s) {len(iframes)} iFrame(s). Tentando mudar para cada um.")
            for i, iframe in enumerate(iframes):
                try:
                    driver.switch_to.frame(iframe)
                    print(f"  --> Mudei para o iFrame {i + 1}.")
                    forms_in_iframe = driver.find_elements(By.TAG_NAME, "form")
                    if forms_in_iframe:
                        print(f"    Formulário(s) encontrado(s) no iFrame {i + 1}:")
                        for j, form in enumerate(forms_in_iframe):
                            print(f"    --- Formulário {j + 1} no iFrame {i + 1} ---")
                            list_fields_in_form(form)
                    else:
                        print(f"    Nenhum formulário direto encontrado no iFrame {i + 1}.")
                        print(f"    Procurando por campos de entrada diretos no iFrame {i + 1}...")
                        list_fields_in_form(driver)
                except Exception as e:
                    print(f"  Erro ao tentar interagir com o iFrame {i + 1}: {e}")
                finally:
                    driver.switch_to.default_content()
                    print(f"  <-- Voltei para o conteúdo principal.")
        else:
            print("Nenhum iFrame encontrado.")

        print("\nProcurando formulários no conteúdo principal da página...")
        forms_main = driver.find_elements(By.TAG_NAME, "form")

        if not forms_main:
            print("Nenhum formulário direto encontrado no conteúdo principal.")
            print("Procurando por campos de entrada soltos (sem um <form> pai explícito)...")
            list_fields_in_form(driver)
            return

        for i, form in enumerate(forms_main):
            print(f"\n--- Formulário {i + 1} (Conteúdo Principal) ---")
            list_fields_in_form(form)

    except Exception as e:
        print(f"Ocorreu um erro: {e}")
    finally:
        if driver:
            driver.quit()
            print("\nNavegador fechado.")

def list_fields_in_form(parent_element):
    """
    Função auxiliar para listar campos dentro de um elemento pai (form ou driver).
    """
    fields = parent_element.find_elements(By.XPATH,
        ".//input | .//select | .//textarea | .//*[@name='loginfmt'] | .//*[@name='passwd'] | .//*[@id='emailInput'] | .//*[@id='passwordInput']"
    )

    if not fields:
        print("  Nenhum campo encontrado neste elemento/formulário.")
        return

    for j, field in enumerate(fields):
        tag_name = field.tag_name
        field_type = field.get_attribute("type") if tag_name == "input" else tag_name
        field_name = field.get_attribute("name")
        field_id = field.get_attribute("id")
        field_placeholder = field.get_attribute("placeholder")
        field_aria_label = field.get_attribute("aria-label")

        print(f"  Campo {j + 1}:")
        print(f"    Tag: {tag_name}")
        print(f"    Tipo: {field_type if field_type else 'N/A'}")
        print(f"    Nome (name): {field_name if field_name else 'N/A'}")
        print(f"    ID: {field_id if field_id else 'N/A'}")
        print(f"    Placeholder: {field_placeholder if field_placeholder else 'N/A'}")
        print(f"    Aria-label: {field_aria_label if field_aria_label else 'N/A'}")

if __name__ == "__main__":
    # URL de exemplo
    target_url = "https://login.microsoftonline.com/"

    # --- Configurações do Proxy (SUBSTITUA PELAS SUAS INFORMAÇÕES) ---
    # EXEMPLO: Se você tem um proxy em "10.0.0.1" na porta "8888"
    my_proxy_address = "IP_DO_SEU_PROXY"  # Ex: "10.0.0.1" ou "proxy.example.com"
    my_proxy_port = 8080                 # Ex: 8888
    my_proxy_username = None             # Ex: "seu_usuario" (se o proxy exigir)
    my_proxy_password = None             # Ex: "sua_senha" (se o proxy exigir)

    # Para testar, você pode usar um proxy público (cuidado com a segurança e a velocidade):
    # Procure por "free http proxy list" no Google para encontrar IPs e portas.
    # Exemplo (pode não estar funcionando):
    # my_proxy_address = "185.199.100.1"
    # my_proxy_port = 8080

    list_office365_form_fields_with_proxy(
        target_url,
        proxy_address=my_proxy_address,
        proxy_port=my_proxy_port,
        proxy_username=my_proxy_username,
        proxy_password=my_proxy_password
    )