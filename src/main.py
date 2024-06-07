import os
import threading
import time
import requests
from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    WebDriverException, NoSuchDriverException, TimeoutException, NoSuchElementException
)
from webdriver_manager.chrome import ChromeDriverManager

# Configuration
CHROME_VERSION = '124.0.6367.78'
NODEPAY_EXTENSION_ID = 'lgmpfmgeabnnlemejacfljbmonaomfmm'
REKTCAPTCHA_EXTENSION_ID = 'bbdhfoclddncoaomddgkaaphcnddbpdh'
NODEPAY_EXTENSION_OUTPUT_FILE = "nodepay_extension.crx"
REKTCAPTCHA_EXTENSION_OUTPUT_FILE = "rektcaptcha_extension.crx"
LOGIN_URL = 'https://app.nodepay.ai/'
REKTCAPTCHA_SETTING_URL = f'chrome-extension://{REKTCAPTCHA_EXTENSION_ID}/popup.html'
NODEPAY_EXTENSION_PAGE = f'chrome-extension://{NODEPAY_EXTENSION_ID}/index.html'

# Environment variables
USER = os.getenv('NODEPAY_USER', '')
PASSW = os.getenv('NODEPAY_PASS', '')
PROXY = os.getenv('NODEPAY_PROXY', '')
ALLOW_DEBUG = os.getenv('ALLOW_DEBUG', 'False').lower() in ('true', '1', 't')
IMGUR_CLIENT_ID = os.getenv('IMGUR_CLIENT_ID', '')

if not USER or not PASSW:
    raise EnvironmentError(
        'Please set NODEPAY_USER and NODEPAY_PASS env variables')

if ALLOW_DEBUG:
    print('Debugging is enabled! This will generate a screenshot and console logs on error!')
    if not IMGUR_CLIENT_ID:
        raise EnvironmentError(
            'Please set IMGUR_CLIENT_ID env variables')



def check_exists_by_xpath(driver, xpath):
    try:
        driver.find_element(By.XPATH, xpath)
        return True
    except:
        return False


def download_crx(extension_id, output_file, chrome_version):
    """Download Chrome extension .crx file"""
    url_template = "https://clients2.google.com/service/update2/crx?response=redirect&prodversion={}&acceptformat=crx2,crx3&x=id%3D{}%26uc"
    url = url_template.format(chrome_version, extension_id)
    headers = {
        'User-Agent': f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36"
    }
    response = requests.get(url, headers=headers,
                            allow_redirects=True, stream=True)
    if response.status_code == 200:
        with open(output_file, 'wb') as file:
            file.write(response.content)
        print(
            f"Extension {extension_id} has been downloaded as {output_file}.")
    else:
        raise Exception(
            f"Failed to download the extension. Status code: {response.status_code}")


# Function to generate error report
def generate_error_report(driver):
    if not ALLOW_DEBUG:
        return

    try:
        # Take a screenshot
        screenshot_path = 'error.png'
        driver.save_screenshot(screenshot_path)
        print('Screenshot taken.')

        # Get console logs
        logs = driver.get_log('browser')
        log_path = 'error.log'
        with open(log_path, 'w') as f:
            for log in logs:
                f.write(str(log))
                f.write('\n')
        print('Console logs saved.')

        # Upload the screenshot to Imgur
        url = 'https://api.imgur.com/3/upload'
        headers = {'Authorization': f'Client-ID {IMGUR_CLIENT_ID}'}
        with open(screenshot_path, 'rb') as image_file:
            files = {'image': image_file}
            response = requests.post(url, headers=headers, files=files)

        if response.status_code == 200:
            data = response.json()
            image_url = data['data']['link']
            print('Screenshot uploaded successfully.')
            print('Image URL:', image_url)
        else:
            print(f'Failed to upload screenshot. Status code: {response.status_code}')
            print('Response:', response.text)

        print('Error report generated! Provide the above information to the developer for debugging purposes.')

    except Exception as e:
        print(f'An error occurred while generating the error report: {str(e)}')


def configure_driver():
    """Configure Chrome WebDriver options"""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument('--no-sandbox')
    options.add_extension(REKTCAPTCHA_EXTENSION_OUTPUT_FILE)
    options.add_extension(NODEPAY_EXTENSION_OUTPUT_FILE)
    if PROXY:
        print('Proxy detected, setting proxy to:', PROXY)
        options.add_argument(f'--proxy-server={PROXY}')
    return options


def start_driver(options):
    """Start the Chrome WebDriver with the specified options"""
    try:
        driver = webdriver.Chrome(options=options)
    except (WebDriverException, NoSuchDriverException):
        print('Could not start with Manager! Trying to default to manual path...')
        try:
            driver_path = "/usr/bin/chromedriver"
            service = ChromeService(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=options)
        except (WebDriverException, NoSuchDriverException):
            raise RuntimeError('Could not start with manual path! Exiting...')
    return driver


def set_desktop_resolution(driver, width=1024, height=768):
    """Set the resolution of the browser window"""
    driver.set_window_size(width, height)


def login(driver, user, password):
    """Log in to the NodePay application"""
    driver.get(LOGIN_URL)
    set_desktop_resolution(driver)
    sleep = 0
    while True:
        try:
            close_button = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//button[@aria-label="Close"]'))
            )
            if close_button.is_displayed():
                close_button.click()
                print('Close button clicked! Proceeding with login.')
                continue
        except (TimeoutException, NoSuchElementException):
            pass

        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//*[@id="basic_user"]'))
            )
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//*[@id="basic_password"]'))
            )
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//*[@type="submit"]'))
            )
            break
        except TimeoutException:
            time.sleep(1)
            print('Loading login form...')
            sleep += 1
            if sleep > 15:
                raise TimeoutException('Could not load login form! Exiting...')

    print('Waiting for captcha to be solved...')
    wait_capcha_solved(driver)
    driver.find_element(By.XPATH, '//*[@id="basic_user"]').send_keys(user)
    driver.find_element(
        By.XPATH, '//*[@id="basic_password"]').send_keys(password)
    driver.find_element(By.XPATH, '//*[@type="submit"]').click()

    sleep = 0
    while True:
        try:
            driver.find_element(By.XPATH, '//*[contains(text(), "Connect")]')
            break
        except:
            time.sleep(1)
            print('Logging in...')
            sleep += 1
            if sleep > 30:
                raise TimeoutException(
                    'Could not login! Double check your username and password! Exiting...')


def enable_auto_capcha():
    """Enable automatic captcha solving using the reCAPTCHA extension"""
    driver.get(REKTCAPTCHA_SETTING_URL)
    set_desktop_resolution(driver)
    sleep = 0
    while True:
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '[data-settings="recaptcha_auto_open"]'))
            )
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '[data-settings="recaptcha_auto_solve"]'))
            )
            break
        except TimeoutException:
            time.sleep(1)
            print('Loading reCAPTCHA extension...')
            sleep += 1
            if sleep > 15:
                raise TimeoutException(
                    'Could not load reCAPTCHA form! Exiting...')

    driver.find_element(
        By.CSS_SELECTOR, '[data-settings="recaptcha_auto_open"]').click()
    driver.find_element(
        By.CSS_SELECTOR, '[data-settings="recaptcha_auto_solve"]').click()


def wait_capcha_solved(driver):
    """Wait for the captcha to be solved using image recognition"""
    sleep = 0
    mainWin = driver.current_window_handle  

    # Move the driver to the first iFrame
    driver.switch_to.frame(driver.find_elements(By.TAG_NAME, "iframe")[0])

    while True:
        try:
            if check_exists_by_xpath(driver, '//span[@aria-checked="true"]'):
                print('Captcha solved!')
                break
        except Exception as e:
            pass
        
        time.sleep(2)
        print('Solving captcha...')
        sleep += 1
        
        if sleep > 100:
            raise TimeoutException('Could not resolve captcha! Exiting...')
    
    # ***************** Back to main window **************************************
    driver.switch_to.window(mainWin)

def wait_for_dashboard(driver):
    """Access nodepay extension page"""
    driver.get(NODEPAY_EXTENSION_PAGE)
    """Wait for the dashboard to load after logging in"""
    sleep = 0
    while True:
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//a[contains(@class, "rounded-lg") and contains(@href, "dashboard")]/span[contains(text(), "Open Dashboard")]'))
            )
            print('Found the "Open Dashboard" link!')
            break
        except Exception as e:
            time.sleep(1)
            print('Loading connection...', e)
            sleep += 1
            if sleep > 30:
                raise TimeoutException('Could not load connection! Exiting...')


def get_data(driver):
    """Retrieve data from the dashboard"""
    try:
        network_quality_element = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located(
                (By.XPATH, "//span[contains(text(), 'Network Quality')]"))
        )
        network_quality = network_quality_element.text.split(":")[1].strip()
    except Exception as e:
        network_quality = False
        print(f'Could not get network quality: {e}')
        generate_error_report(driver)

    try:
        earnings_element = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located(
                (By.XPATH, "//div[@class='h-[64px] bg-grey-primary rounded-lg py-3 px-6 flex flex-col items-center justify-between']/div/span[@class='text-16px font-bold mr-1 truncate']"))
        )
        epoch_earnings = earnings_element.text
    except Exception as e:
        epoch_earnings = False
        print(f'Could not get earnings: {e}')
        generate_error_report(driver)

    try:
        badges = WebDriverWait(driver, 10).until(
            EC.visibility_of_all_elements_located(
                (By.XPATH, "//span[@class='font-bold text-green']"))
        )
        connected = badges[0].text if badges else False
    except Exception as e:
        connected = False
        print(f'Could not get connection status: {e}')
        generate_error_report(driver)

    return {'connected': connected, 'network_quality': network_quality, 'epoch_earnings': epoch_earnings}

def refresh_task(driver):
    print("Refresh task started....")
    try:
        while True:
            data = get_data(driver)
            print(data)
            time.sleep(30)  # Wait for 30 seconds
            driver.refresh()  # Refresh the page

    except KeyboardInterrupt:
        print("Selenium task stopped by user")

    finally:
        driver.quit()

app = Flask(__name__)


@app.route('/')
def get_endpoint():
    """API endpoint to get data"""
    try:
        data = get_data(driver)
        for key in data:
            if data[key] is None:
                data[key] = False
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print('Downloading extension rektcaptcha...')
    download_crx(REKTCAPTCHA_EXTENSION_ID,
                 REKTCAPTCHA_EXTENSION_OUTPUT_FILE, CHROME_VERSION)
    print('Downloading extension nodepay...')
    download_crx(NODEPAY_EXTENSION_ID,
                 NODEPAY_EXTENSION_OUTPUT_FILE, CHROME_VERSION)
    print('Downloaded! Installing extension and driver manager...')

    options = configure_driver()
    driver = start_driver(options)

    print('Started! Logging in...')
    try:
        enable_auto_capcha()
        login(driver, USER, PASSW)
        print('Logged in! Waiting for connection...')
        wait_for_dashboard(driver)
        # Start the Selenium task in a separate thread
        selenium_thread = threading.Thread(target=refresh_task, args=(driver,))
        selenium_thread.start()
        print('Connected! Starting API...')
        app.run(host='0.0.0.0', port=80, debug=False)
    except Exception as e:
        print(f'An error occurred: {e}')
        generate_error_report(driver)
    finally:
        driver.quit()
