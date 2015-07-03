from django.test import LiveServerTestCase
from django.test.utils import override_settings
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

import os
import time

@override_settings(DEBUG=True, EMAIL_BACKEND="djrill.mail.backends.djrill.DjrillBackend")
class NewVisitorTest(LiveServerTestCase):

    def setUp(self):
        self.browser = webdriver.Firefox()
        self.browser.implicitly_wait(3)

    def tearDown(self):
        self.browser.quit()

    def test_new_visitor_to_site_non_mobile(self):
        self.browser.maximize_window()
        # Jeremy heard about a new site called usecirca.com and figured he see what all the hub-bub was
        self.browser.get(self.live_server_url)

        # Upon arrival, Jeremy is greeted by a flashy design and a bitchin' logo
        self.assertIn('Circa - Buy and Sell Locally', self.browser.title)
        jumbotron_text = self.browser.find_element_by_tag_name('h1').text
        self.assertIn('Buy and Sell in Atlanta', jumbotron_text)

        # "Wow", exclaims Jeremy, "I need to make an account right-stat-now!"
        # It's at this point that Jeremy navigates to the Sign-up page
        sign_up_button = self.browser.find_element_by_id("sign-up-large")
        sign_up_button.click()

        # Jeremy now sees the form by which he can create an account.  Being savvy to the world,
        # he opts to create an account with email instead of using Facebook
        header_text = self.browser.find_element_by_tag_name('h1').text
        self.assertIn('Sign up for Circa', header_text)

        # Jeremy puts in his information and submits so that he may begin his wonderful journey on Circa
        username_field = self.browser.find_element_by_id('id_username')
        username_field.send_keys('jeremyizkewl')
        email_field = self.browser.find_element_by_id('id_email')
        email_field.send_keys('jeremy@example.com')
        password_field = self.browser.find_element_by_id('id_password1')
        password_field.send_keys('pooploop')
        password_confirm_field = self.browser.find_element_by_id('id_password2')
        password_confirm_field.send_keys('pooploop')
        password_confirm_field.send_keys(Keys.ENTER)

        # Gleefully, Jeremy sees that his new user name is up in the corner and that he is now logged in
        user_button = self.browser.find_element_by_id('username-large')
        user_text = user_button.text
        self.assertIn('jeremyizkewl', user_text)

        # Now that he has an account, Jeremy wanted to post something and see if he could make a quick buck
        sell_button = self.browser.find_element_by_id('sell-large')
        sell_button.click()
        sell_header_text = self.browser.find_element_by_tag_name('h1').text
        self.assertIn('List an item for sale', sell_header_text)

        # After searching through his old knick-knacks, Jeremy finds the perfect item to sell
        title_field = self.browser.find_element_by_id('id_title')
        title_field.send_keys('Dragon Dildo')
        description_field = self.browser.find_element_by_id('id_description')
        description_field.send_keys('Lightly used, originally bought at a garage sale.  Can\'t confirm if a dragon\'s '
                                    'penis actually looks like this.')
        category_field = Select(self.browser.find_element_by_id('id_category'))
        category_field.select_by_value('5')
        photo_field = self.browser.find_element_by_id('id_photo')
        photo_field.send_keys(os.getcwd() + '\\functional_tests\\func_test_image.jpg')
        self.browser.find_element_by_id('list-item-button').click()

        # Titillating from the excitement of posting an item, Jeremy swiftly punches in his price and
        # a valid zip code
        listing_header_text = self.browser.find_element_by_tag_name('h1').text
        self.assertIn('Create a listing', listing_header_text)
        starting_offer_field = self.browser.find_element_by_id('id_starting_offer')
        starting_offer_field.send_keys('100')
        buy_now_field = self.browser.find_element_by_id('id_buy_now_price')
        buy_now_field.send_keys('140')
        zipcode_field = self.browser.find_element_by_id('id_zipcode')
        zipcode_field.send_keys('30313')
        zipcode_field.send_keys(Keys.ENTER)

        # Alas, all his hard work paid off and Jeremy beheld his post in all its glory
        listing_title_text = self.browser.find_element_by_id('title-large').text
        self.assertIn('Dragon Dildo', listing_title_text)

        # Having had adequate time to behold his handy work, Jeremy heads back to the home page
        logo_button = self.browser.find_element_by_id('logo')
        logo_button.click()

        # From the home page, Jeremy can clearly see his new post and is hopeful that somebody buys it soon
        page_text = self.browser.find_element_by_tag_name('body').text
        self.assertIn("Dragon Dildo", page_text)

        # Satisfied that he now has an account and has posted his item, Jeremy logs out of Circa and sprints
        # to the door, anxious to tell his friends of his new find
        user_button = self.browser.find_element_by_id('username-large')
        user_button.click()
        logout_button = self.browser.find_element_by_id('logout-large')
        logout_button.click()
        jumbotron_text = self.browser.find_element_by_tag_name('h1').text
        self.assertIn('Buy and Sell in Atlanta', jumbotron_text)
