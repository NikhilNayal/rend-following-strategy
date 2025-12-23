
from SmartApi import SmartConnect
import os
import pyotp
from typing import Dict, Any

class AngelClient:
    def __init__(self):
        self.api_key = os.getenv("ANGEL_API_KEY")
        self.client_code = os.getenv("ANGEL_CLIENT_CODE")
        self.password = os.getenv("ANGEL_API_SECRET") # Using SECRET as PIN/Pass? Usually it's PIN.
        # User env has ANGEL_API_SECRET. Usually SmartApi needs API Key, Client Code, Password, TOTP.
        # I will assume ANGEL_API_SECRET is the password/pin or needed for session.
        # Wait, usually it is: 
        # smartApi = SmartConnect(api_key="...")
        # data = smartApi.generateSession(clientCode, password, totp)
        self.totp_secret = os.getenv("ANGEL_TOTP_SECRET")
        self.smart_api = SmartConnect(api_key=self.api_key)
        self.session = None

    def login(self):
        try:
            # Clean secret (remove spaces/newlines often introduced by copy-paste)
            if not self.totp_secret:
                print("Angel One Login Error: TOTP Secret is missing in env.")
                return
                
            clean_secret = self.totp_secret.replace(" ", "").strip()
            totp = pyotp.TOTP(clean_secret).now()
            # The password arg in generateSession is actually the PIN or Password.
            # I'll assume ANGEL_API_SECRET acts as the password here based on variable naming, or I might need a PIN.
            # Looking at .env, there is no explicit PIN, just API_SECRET. 
            # Often users put PIN in a variable. 
            # I will try using ANGEL_API_SECRET as the password.
            data = self.smart_api.generateSession(self.client_code, self.password, totp)
            if data['status']:
                self.session = data
                print("Angel One Login Successful")
            else:
                print(f"Angel One Login Failed: {data['message']}")
        except Exception as e:
            print(f"Angel One Login Error: {e}")

    def place_order(self, symbol: str, token: int, transaction_type: str, quantity: int, product_type: str = "CARRYFORWARD") -> str:
        """
        Place an order on Angel One.
        
        Args:
            symbol: Trading symbol (e.g., 'BANKNIFTY26JAN54000CE')
            token: Instrument token (integer)
            transaction_type: 'BUY' or 'SELL'
            quantity: Number of contracts
            product_type: 'CARRYFORWARD' for options
            
        Returns:
            Order ID if successful, None otherwise
        """
        if not self.session:
            self.login()
        
        try:
            orderparams = {
                "variety": "NORMAL",
                "tradingsymbol": symbol,  # Trading symbol string
                "symboltoken": str(token),  # Token as string
                "transactiontype": transaction_type,
                "exchange": "NFO",
                "ordertype": "MARKET",
                "producttype": product_type,
                "duration": "DAY",
                "quantity": str(quantity)  # Quantity as string
            }
            
            print(f"Placing {transaction_type} order: {symbol} (Token: {token}) Qty: {quantity}")
            orderid = self.smart_api.placeOrder(orderparams)
            
            if orderid:
                print(f"Order placed successfully. Order ID: {orderid}")
            return orderid
            
        except Exception as e:
            print(f"Order Placement Failed for {symbol}: {e}")
            return None

    def get_positions(self):
        if not self.session:
            self.login()
        try:
            return self.smart_api.position()
        except Exception as e:
            print(f"Error fetching positions: {e}")
            return None
