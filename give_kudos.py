import os
import time
from playwright.sync_api import sync_playwright, TimeoutError

BASE_URL = "https://www.strava.com/"

class StravaAutomator:
    def __init__(self, max_run_duration=600, max_wait_suggest=5) -> None:  
        self.EMAIL = os.environ.get('STRAVA_EMAIL')
        self.PASSWORD = os.environ.get('STRAVA_PASSWORD')

        if self.EMAIL is None or self.PASSWORD is None:
            raise Exception(f"Must set environ variables EMAIL AND PASSWORD. \
                e.g. run export STRAVA_EMAIL=YOUR_EMAIL")
        self.max_run_duration = max_run_duration
        self.max_wait_suggest = max_wait_suggest
        self.start_time = time.time()
        self.num_entries = 100
        self.web_feed_entry_pattern = '[data-testid=web-feed-entry]'
        self.follow_button_pattern = '.packages-dashboard-ui-src-components-YourSuggestedFollows-YourSuggestedFollows-module__followButton--DPkgm'

        p = sync_playwright().start()
        self.browser = p.firefox.launch()
        self.page = self.browser.new_page()
        self.page.set_default_timeout(60000)  # Increase default timeout to 60 seconds
        self.own_profile_id = None

    def email_login(self):
        try:
            self.page.goto(os.path.join(BASE_URL, 'login'))
            self.page.fill('#email', self.EMAIL)
            self.page.fill("#password", self.PASSWORD)
            self.page.click("button[type='submit']")
            # Wait for navigation after login
            self.page.wait_for_load_state('networkidle')
            print("---Logged in!!---")
        except TimeoutError:
            print("Login timeout - retrying...")
            self.page.reload()
            time.sleep(2)
            self.email_login()

    def run_automation(self):
        self.give_kudos()  # Run kudos first
        self.click_follow_buttons()  # Then run follow

    def give_kudos(self):
        print("\n---Starting to give kudos---")
        try:
            self._get_page_and_own_profile()
            web_feed_entry_locator = self.page.locator(self.web_feed_entry_pattern)
            self.locate_kudos_buttons_and_maybe_give_kudos(web_feed_entry_locator=web_feed_entry_locator)
        except TimeoutError:
            print("Timeout while loading feed - retrying...")
            time.sleep(2)
            self.give_kudos()
            
    def click_follow_buttons(self):
        print("---Starting to follow users---")
        follows_count = 0
        wait_start_time = None
        
        while time.time() - self.start_time < self.max_run_duration:
            buttons = self.page.locator(self.follow_button_pattern)
            count = buttons.count()
            
            if count == 0:
                if wait_start_time is None:
                    wait_start_time = time.time()
                    print("\nNo Follow buttons found. Waiting for new suggestions...")
                
                if time.time() - wait_start_time >= self.max_wait_suggest:
                    print(f"No new suggestions after {self.max_wait_suggest} seconds. Exiting...")
                    return
                
                time.sleep(1)
                continue
            else:
                wait_start_time = None
                
            for i in range(count):
                if time.time() - self.start_time >= self.max_run_duration:
                    print(f"\nTime limit reached. Total follows: {follows_count}")
                    return
                    
                button = buttons.nth(i)
                try:
                    button.click(timeout=1000)
                    follows_count += 1
                    print("=", end="", flush=True)
                    time.sleep(1)
                except:
                    continue
                
            time.sleep(0.5)
            
        print(f"\nFollow phase finished. Total follows: {follows_count}")

    def _get_page_and_own_profile(self):
        try:
            self.page.goto(os.path.join(BASE_URL, f"dashboard?num_entries={self.num_entries}"), 
                          wait_until='domcontentloaded')
            
            self.page.wait_for_selector(self.web_feed_entry_pattern, timeout=60000)
            
            for _ in range(5):
                self.page.keyboard.press('PageDown')
                time.sleep(0.5)
                self.page.keyboard.press('PageUp')

            self.own_profile_id = self.page.locator(".user-menu > a").get_attribute('href').split("/athletes/")[1]
            print("Got profile ID:", self.own_profile_id)
        except Exception as e:
            print(f"Error loading dashboard: {str(e)}")
            raise

    def locate_kudos_buttons_and_maybe_give_kudos(self, web_feed_entry_locator) -> int:
        w_count = web_feed_entry_locator.count()
        given_count = 0
        print(f"Found {w_count} feed entries")
        
        for i in range(w_count):
            if time.time() - self.start_time > self.max_run_duration:
                print("Max run duration reached.")
                break

            try:
                web_feed = web_feed_entry_locator.nth(i)
                p_count = web_feed.get_by_test_id("entry-header").count()

                if self.is_club_post(web_feed):
                    print('c', end='')
                    continue

                if p_count > 1:
                    for j in range(p_count):
                        participant = web_feed.get_by_test_id("entry-header").nth(j)
                        if not self.is_participant_me(participant):
                            kudos_container = web_feed.get_by_test_id("kudos_comments_container").nth(j)
                            button = self.find_unfilled_kudos_button(kudos_container)
                            given_count += self.click_kudos_button(unfilled_kudos_container=button)
                else:
                    if not self.is_participant_me(web_feed):
                        button = self.find_unfilled_kudos_button(web_feed)
                        given_count += self.click_kudos_button(unfilled_kudos_container=button)
            except Exception as e:
                print(f"\nError processing entry {i}: {str(e)}")
                continue
                    
        print(f"\nKudos given: {given_count}")
        return given_count

    def is_club_post(self, container) -> bool:
        return (container.get_by_test_id("group-header").count() > 0 or 
                container.locator(".clubMemberPostHeaderLinks").count() > 0)

    def is_participant_me(self, container) -> bool:
        owner = self.own_profile_id
        try:
            h = container.get_by_test_id("owners-name").get_attribute('href')
            owner = h.split("/athletes/")[1]
        except:
            print("Issue getting owners-name container.")
        return owner == self.own_profile_id

    def find_unfilled_kudos_button(self, container):
        try:
            return container.get_by_test_id("unfilled_kudos")
        except:
            return None

    def click_kudos_button(self, unfilled_kudos_container) -> int:
        if unfilled_kudos_container and unfilled_kudos_container.count() == 1:
            try:
                unfilled_kudos_container.click(timeout=2000, no_wait_after=True)
                print('=', end='')
                time.sleep(1)
                return 1
            except:
                return 0
        return 0

    def cleanup(self):
        self.browser.close()

def main():
    automator = StravaAutomator(max_run_duration=600, max_wait_suggest=5)
    try:
        automator.email_login()
        automator.run_automation()
    finally:
        automator.cleanup()

if __name__ == "__main__":
    main()
