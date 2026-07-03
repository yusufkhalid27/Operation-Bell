import undetected_chromedriver as uc
from gen_data import generate_email, generate_first_last_name
from otp_imap import wait_for_otp
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
import time
import random
import string

# TODO: Got 403'd by taco bell, need to figure out how to bypass that. Maybe use a proxy or something?
# TODO: Add a typing method, so email and otp are typed in like a human would, instead of just being sent all at once. This might help with the 403 issue.
# TODO: They use Akamai for bot protection, so maybe we can use undetected-chromedriver to bypass that?

def type_like_human(element, text, incorrect_keys=True):
    for char in text:
        ran_char_seed = random.randint(0, 100)
        if ran_char_seed < 13 and incorrect_keys:  # 13% chance to type an incorrect character
            element.send_keys(random.choice(string.ascii_letters + string.digits))
            random_delay(0.05, 0.2)
            element.send_keys('\b')
            random_delay(0.05, 0.2)
        element.send_keys(char)
        random_delay(0.05, 0.2)

def _element_center_in_viewport(driver, element):
    return driver.execute_script(
        """
        const r = arguments[0].getBoundingClientRect();
        return {
            x: Math.floor(r.left + r.width / 2),
            y: Math.floor(r.top + r.height / 2),
        };
        """,
        element,
    )

def move_mouse_in_steps(driver, src_el, dst_el, click=False, steps=20, total_seconds=0.3):
    if steps < 1:
        steps = 1

    src = _element_center_in_viewport(driver, src_el)
    dst = _element_center_in_viewport(driver, dst_el)

    per_step = max(total_seconds / steps, 0.0)
    chain = ActionChains(driver)

    # Start at the source element center.
    chain.move_to_element(src_el)

    last_x = src["x"]
    last_y = src["y"]

    for i in range(1, steps + 1):
        t = i / steps
        target_x = round(src["x"] + (dst["x"] - src["x"]) * t)
        target_y = round(src["y"] + (dst["y"] - src["y"]) * t)

        dx = int(target_x - last_x)
        dy = int(target_y - last_y)
        if dx != 0 or dy != 0:
            chain.move_by_offset(dx, dy)
            last_x = target_x
            last_y = target_y

        if per_step:
            chain.pause(per_step)

    chain.perform()
    if click:
        ActionChains(driver).click().perform()

def random_delay(min_delay=0.5, max_delay=1.5):
    time.sleep(random.uniform(min_delay, max_delay))

def wait_for_css(driver, selector, timeout=20, visible=True):
    condition = (
        EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
        if visible
        else EC.presence_of_element_located((By.CSS_SELECTOR, selector))
    )
    return WebDriverWait(driver, timeout).until(condition)

if __name__ == "__main__":
    driver = uc.Chrome()
    driver.get('https://www.tacobell.com/register/yum')

    # EMAIL SCREEN
    email_input = driver.find_element("css selector", "input[name='email']")
    move_mouse_in_steps(driver, driver.find_element("tag name", "body"), email_input, click=True,steps=random.randint(10, 30), total_seconds=random.uniform(0.5, 1.2))
    gen_email = generate_email()
    type_like_human(email_input, gen_email)

    random_delay(0.5, 1)
    confirm_email = driver.find_element("xpath", "//button[contains(text(), 'Confirm')]")
    move_mouse_in_steps(driver, email_input, confirm_email, click=True, steps=random.randint(5, 10), total_seconds=random.uniform(0.3, 0.6))

    # OTP SCREEN
    otp = str(wait_for_otp(recipient=gen_email, include_seen=True, mark_seen=True))
    otp_input = driver.find_element("css selector", "input[name='code']")
    move_mouse_in_steps(driver, driver.find_element("tag name", "body"), otp_input, click=True, steps=random.randint(10, 30), total_seconds=random.uniform(0.5, 1.2))
    type_like_human(otp_input, otp, incorrect_keys=False)
    
    random_delay(0.5, 1)
    confirm_otp = driver.find_element("xpath", "//button[contains(text(), 'Confirm')]")
    move_mouse_in_steps(driver, otp_input, confirm_otp, click=True, steps=random.randint(5, 10), total_seconds=random.uniform(0.3, 0.6))
    
    # INFO SCREEN
    first_name, last_name = generate_first_last_name()
    first_name_input = WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[name='first_name']")))
    move_mouse_in_steps(driver, driver.find_element("tag name", "body"), first_name_input, click=True, steps=random.randint(10, 30), total_seconds=random.uniform(0.5, 1.2))
    type_like_human(first_name_input, first_name)
    
    last_name_input = driver.find_element("css selector", "input[name='last_name']")
    move_mouse_in_steps(driver, first_name_input, last_name_input, click=True, steps=random.randint(10, 30), total_seconds=random.uniform(0.3, 0.7))
    type_like_human(last_name_input, last_name)

    birthday_input = driver.find_element("css selector", "input[name='birthday']")
    move_mouse_in_steps(driver, last_name_input, birthday_input, click=True, steps=random.randint(10, 30), total_seconds=random.uniform(0.5, 0.7))
    type_like_human(birthday_input, f'0{random.randint(1,9)}0{random.randint(1,9)}', incorrect_keys=False)

    agree_tick = driver.find_element("css selector", "input[name='agreement']")
    move_mouse_in_steps(driver, birthday_input, agree_tick, click=True, steps=random.randint(5, 10), total_seconds=random.uniform(0.3, 0.6))
    
    confirm_details = driver.find_element("xpath", "//button[contains(text(), 'Confirm')]")
    move_mouse_in_steps(driver, agree_tick, confirm_details, click=True, steps=random.randint(5, 10), total_seconds=random.uniform(0.3, 0.6))

    # PHONE NUMBER SCREEN
    no_phone_link = WebDriverWait(driver, 60).until(EC.visibility_of_element_located((By.XPATH, "//a[contains(text(), 'Continue Using Email to Log In')]")))
    move_mouse_in_steps(driver, driver.find_element("tag name", "body"), no_phone_link, click=True, steps=random.randint(10, 30), total_seconds=random.uniform(0.5, 1.2))

    with open("accounts.txt", "a", encoding="utf-8", newline="") as f:
        f.write(f"{gen_email}, {first_name} {last_name}, {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.flush()
        f.close()
    