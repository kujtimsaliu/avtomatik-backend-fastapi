import re
import json
from typing import Dict, List, Tuple, Set, Optional, Any
import Levenshtein
from sqlalchemy.orm import Session

from models import Product, Store, Pricing


class ProductMatcher:
    def __init__(self, db_session: Session):
        self.db = db_session

        # Common monitor brands for quick lookups
        self.known_brands = {
            "lg", "samsung", "dell", "aoc", "benq", "asus", "msi", "xiaomi",
            "philips", "acer", "viewsonic", "hp", "lenovo", "gigabyte", "fuego"
        }

        # Common display panel types
        self.panel_types = {"ips", "va", "tn", "oled", "qd-oled", "nano ips"}

        # Common resolution identifiers
        self.resolution_patterns = {
            "fhd": "1920x1080",
            "full hd": "1920x1080",
            "1080p": "1920x1080",
            "wqhd": "2560x1440",
            "qhd": "2560x1440",
            "1440p": "2560x1440",
            "2k": "2560x1440",
            "4k": "3840x2160",
            "uhd": "3840x2160",
            "uwqhd": "3440x1440",
            "ultrawide qhd": "3440x1440",
            "5k": "5120x2880"
        }

    def process_anhoch_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process Anhoch product data and extract structured data."""
        processed_products = []

        # Create or get store
        store = self._get_or_create_store("Anhoch", "https://www.anhoch.com")

        for item in data.get("products", []):
            # Extract product attributes
            processed_product = self._parse_monitor_attributes(item["name"])

            # Additional fields
            processed_product["original_data"] = item
            processed_product["price"] = self._extract_price(item["price"])
            processed_product["stock_status"] = item.get("stock", "Unknown")
            processed_product["url"] = item["url"]
            processed_product["image_url"] = item["imageUrl"]
            processed_product["store"] = store

            processed_products.append(processed_product)

        return processed_products

    def process_neptun_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process Neptun product data and extract structured data."""
        processed_products = []

        # Create or get store
        store = self._get_or_create_store("Neptun", "https://www.neptun.mk")

        for item in data.get("products", []):
            # Extract product attributes
            processed_product = self._parse_monitor_attributes(item["name"])

            # Additional fields
            processed_product["original_data"] = item
            processed_product["price"] = self._extract_price(item["price"])
            processed_product["stock_status"] = item.get("stock", "Unknown")
            processed_product["url"] = item["url"]
            processed_product["image_url"] = item["imageUrl"]
            processed_product["store"] = store

            processed_products.append(processed_product)

        return processed_products

    def _get_or_create_store(self, name: str, website: str) -> Store:
        """Get existing store or create a new one"""
        store = self.db.query(Store).filter(Store.name == name).first()
        if not store:
            store = Store(name=name, website=website)
            self.db.add(store)
            self.db.commit()
        return store

    def _parse_monitor_attributes(self, product_name: str) -> Dict[str, Any]:
        """Extract structured data from a monitor product name."""
        product_name = product_name.strip()
        result = {
            "name": product_name,
            "brand": None,
            "model": None,
            "size": None,
            "resolution": None,
            "refresh_rate": None,
            "panel_type": None,
            "specs": {},
        }

        # Convert to lowercase for processing but preserve original case
        name_lower = product_name.lower()

        # Extract size (typically in format: XX" or XX-inch)
        size_match = re.search(r'(\d{1,2}(?:\.\d)?)["\']|\b(\d{1,2}(?:\.\d)?)\s*(?:inch|инч)', name_lower)
        if size_match:
            size_value = size_match.group(1) if size_match.group(1) else size_match.group(2)
            if size_value:
                result["size"] = float(size_value)
                result["specs"]["size"] = float(size_value)

        # Extract brand
        for brand in self.known_brands:
            if brand.lower() in name_lower:
                # Use word boundaries to avoid partial matches
                if re.search(r'\b' + re.escape(brand.lower()) + r'\b', name_lower):
                    result["brand"] = brand.upper() if brand.lower() in ["lg", "hp", "msi", "aoc"] else brand.capitalize()
                    break

        # Extract model number - look for patterns like specific formats
        # Dell pattern: P2425H, SE2422H, U2724DE
        # Samsung pattern: LS27C360EAUXEN, LF24T450FQRXEN
        # LG pattern: 24GQ50F-B, 27MP60GP-B

        # Dell model pattern
        if result["brand"] and result["brand"].lower() == "dell":
            dell_model = re.search(r'\b([A-Z]+\d{3,4}[A-Z]{0,2}(?:-[A-Z0-9]+)?)\b', product_name)
            if dell_model:
                result["model"] = dell_model.group(1)

        # Samsung model pattern
        elif result["brand"] and result["brand"].lower() == "samsung":
            samsung_model = re.search(r'\b(L[SCFT]\d{2}[A-Z]\d{3}[A-Z]+)\b', product_name)
            if samsung_model:
                result["model"] = samsung_model.group(1)

        # LG model pattern
        elif result["brand"] and result["brand"].lower() == "lg":
            lg_model = re.search(r'\b(\d{2}[A-Z]{2,}\d{2,}[A-Z]{0,2}-[A-Z0-9]+)\b', product_name)
            if lg_model:
                result["model"] = lg_model.group(1)

        # Generic model pattern for other brands
        if not result["model"] and result["brand"]:
            # Look for alphanumeric pattern after brand name
            generic_model = re.search(
                r'\b' + re.escape(result["brand"].lower()) + r'[^\w]*([A-Z0-9]+-?[A-Z0-9]+(?:-[A-Z0-9]+)?)\b',
                name_lower
            )
            if generic_model:
                result["model"] = generic_model.group(1).upper()

        # If model still not found, look for common model patterns
        if not result["model"]:
            # Look for patterns like: XXX-XXX, XXXXXXXX, etc.
            model_patterns = [
                r'\b([A-Z0-9]{2,}[-_][A-Z0-9]{2,}[-_]?[A-Z0-9]*)\b',  # Format: XX-XX, XX-XX-XX
                r'\b([A-Z]\d{4}[A-Z]*)\b',  # Format: X9999X
                r'\b(\d{2}[A-Z]\d{2,}[A-Z0-9]+)\b',  # Format: 99X99XXX
            ]

            for pattern in model_patterns:
                match = re.search(pattern, product_name, re.IGNORECASE)
                if match:
                    result["model"] = match.group(1).upper()
                    break

        # Extract resolution
        for res_key, res_value in self.resolution_patterns.items():
            if res_key in name_lower:
                result["resolution"] = res_value
                result["specs"]["resolution"] = res_value
                break

        # Extract specific resolution if mentioned in format like 1920x1080
        specific_res = re.search(r'(\d{3,4}x\d{3,4})', name_lower)
        if specific_res:
            result["resolution"] = specific_res.group(1)
            result["specs"]["resolution"] = specific_res.group(1)

        # Extract refresh rate (typically in format: XXHz or XX Hz)
        refresh_match = re.search(r'(\d{2,3})(?:\s*)hz', name_lower)
        if refresh_match:
            result["refresh_rate"] = float(refresh_match.group(1))
            result["specs"]["refresh_rate"] = float(refresh_match.group(1))

        # Extract panel type
        for panel in self.panel_types:
            if panel.lower() in name_lower:
                result["panel_type"] = panel.upper() if panel.lower() in ["ips", "va", "tn"] else panel.upper()
                result["specs"]["panel_type"] = result["panel_type"]
                break

        # Extract additional specs
        additional_specs = {
            "curved": "curved" in name_lower,
            "gaming": "gaming" in name_lower or "game" in name_lower,
            "hdr": "hdr" in name_lower,
            "freesync": "freesync" in name_lower,
            "gsync": "g-sync" in name_lower or "gsync" in name_lower,
            "usb_c": "usb-c" in name_lower or "usbc" in name_lower,
            "hdmi": "hdmi" in name_lower,
            "displayport": "dp" in name_lower or "displayport" in name_lower,
            "speakers": "speaker" in name_lower,
            "height_adjustable": "height" in name_lower or "has" in name_lower,
        }

        # Add found specs to the specs dictionary
        for key, value in additional_specs.items():
            if value:
                result["specs"][key] = value

        return result

    def _extract_price(self, price_str: str) -> float:
        """Extract numeric price from string formats like '9.280,00.' or '4.999.,00 den.'"""
        # Remove non-numeric characters except for decimal separators
        price_clean = re.sub(r'[^\d,.]', '', price_str)

        # Handle Macedonian price format (9.280,00)
        if ',' in price_clean and '.' in price_clean:
            # If both ',' and '.' exist, assume European format
            price_clean = price_clean.replace('.', '')  # Remove thousand separators
            price_clean = price_clean.replace(',', '.')  # Convert decimal separator
        elif ',' in price_clean:
            # If only ',' exists, assume it's the decimal separator
            price_clean = price_clean.replace(',', '.')

        # Try to convert to float
        try:
            return float(price_clean)
        except ValueError:
            return 0.0

    def save_product(self, product_data: Dict[str, Any]) -> Tuple[Product, Pricing]:
        """Save a processed product to the database."""
        # Check if product already exists by brand+model
        existing_product = None
        if product_data["brand"] and product_data["model"]:
            existing_product = self.db.query(Product).filter(
                Product.brand == product_data["brand"],
                Product.model == product_data["model"]
            ).first()

        # If product doesn't exist, create it
        if not existing_product:
            new_product = Product(
                name=product_data["name"],
                brand=product_data["brand"] or "Unknown",
                model=product_data["model"] or "Unknown",
                category="Monitors",
                specs=product_data["specs"],
                size=product_data["size"],
                resolution=product_data["resolution"],
                refresh_rate=product_data["refresh_rate"],
                panel_type=product_data["panel_type"],
                image_url=product_data["image_url"]
            )
            self.db.add(new_product)
            self.db.commit()
            product = new_product
        else:
            product = existing_product

        # Add pricing information
        pricing = Pricing(
            product_id=product.id,
            store_id=product_data["store"].id,
            price=product_data["price"],
            stock_status=product_data["stock_status"],
            url=product_data["url"],
            original_name=product_data["name"],
            original_json=product_data["original_data"]
        )
        self.db.add(pricing)
        self.db.commit()

        return product, pricing

    def find_product_matches(self) -> List[Dict[str, Any]]:
        """Find matching products across different stores."""
        # Get all products without matches
        products = self.db.query(Product).all()
        stores = self.db.query(Store).all()

        matches = []

        # For each product, find potential matches
        for product in products:
            # Get current stores for this product
            current_stores = set(pricing.store_id for pricing in product.pricing)

            # Find stores where this product doesn't exist yet
            missing_stores = [store for store in stores if store.id not in current_stores]

            for store in missing_stores:
                # Look for potential matches in this store
                potential_matches = self._find_potential_matches(product, store)

                for match in potential_matches:
                    # Calculate match score
                    match_score = self._calculate_match_score(product, match)

                    if match_score >= 0.8:  # 80% confidence threshold
                        # Create a pricing entry linking the product to the store
                        pricing = Pricing(
                            product_id=product.id,
                            store_id=store.id,
                            price=match["price"],
                            stock_status=match["stock_status"],
                            url=match["url"],
                            original_name=match["name"],
                            original_json=match["original_data"]
                        )
                        self.db.add(pricing)

                        matches.append({
                            "product": product,
                            "store": store,
                            "match": match,
                            "score": match_score
                        })

        self.db.commit()
        return matches

    def _find_potential_matches(self, product: Product, store: Store) -> List[Dict[str, Any]]:
        """Find potential matches for a product in a specific store."""
        # Get all pricing entries for the store
        store_pricings = self.db.query(Pricing).filter(Pricing.store_id == store.id).all()

        potential_matches = []

        for pricing in store_pricings:
            # Skip if already matched to a product
            if pricing.product_id:
                continue

            # Process the original data if available
            if pricing.original_json:
                match_data = self._parse_monitor_attributes(pricing.original_name)
                match_data["price"] = pricing.price
                match_data["stock_status"] = pricing.stock_status
                match_data["url"] = pricing.url
                match_data["original_data"] = pricing.original_json

                # Check for brand/model match
                if (match_data["brand"] and match_data["brand"].lower() == product.brand.lower() and
                        match_data["model"] and self._model_similarity(match_data["model"], product.model) >= 0.8):
                    potential_matches.append(match_data)

                # Check for size and specs match if no brand/model match
                elif (match_data["size"] and product.size and match_data["size"] == product.size and
                      self._specs_similarity(match_data["specs"], product.specs) >= 0.7):
                    potential_matches.append(match_data)

        return potential_matches

    def _model_similarity(self, model1: str, model2: str) -> float:
        """Calculate similarity between two model numbers using Levenshtein distance."""
        if not model1 or not model2:
            return 0.0

        # Normalize models: uppercase and remove non-alphanumeric chars
        model1_norm = re.sub(r'[^A-Z0-9]', '', model1.upper())
        model2_norm = re.sub(r'[^A-Z0-9]', '', model2.upper())

        if not model1_norm or not model2_norm:
            return 0.0

        # Calculate Levenshtein distance
        distance = Levenshtein.distance(model1_norm, model2_norm)
        max_len = max(len(model1_norm), len(model2_norm))

        # Return similarity score (1 - normalized distance)
        return 1 - (distance / max_len)

    def _specs_similarity(self, specs1: Dict[str, Any], specs2: Dict[str, Any]) -> float:
        """Calculate similarity between two spec dictionaries."""
        if not specs1 or not specs2:
            return 0.0

        # Convert specs to sets for comparison
        keys1 = set(specs1.keys())
        keys2 = set(specs2.keys())

        # Check common keys
        common_keys = keys1.intersection(keys2)

        if not common_keys:
            return 0.0

        # Count matching values
        matches = 0
        for key in common_keys:
            if specs1[key] == specs2[key]:
                matches += 1

        # Calculate similarity score
        return matches / len(common_keys)

    def _calculate_match_score(self, product: Product, match_data: Dict[str, Any]) -> float:
        """Calculate overall match score between a product and potential match."""
        score_components = []

        # Brand match (25%)
        if product.brand and match_data["brand"]:
            brand_match = 1.0 if product.brand.lower() == match_data["brand"].lower() else 0.0
            score_components.append((brand_match, 0.25))

        # Model match (35%)
        if product.model and match_data["model"]:
            model_match = self._model_similarity(product.model, match_data["model"])
            score_components.append((model_match, 0.35))

        # Size match (15%)
        if product.size and match_data["size"]:
            size_match = 1.0 if product.size == match_data["size"] else 0.0
            score_components.append((size_match, 0.15))

        # Resolution match (10%)
        if product.resolution and match_data["resolution"]:
            res_match = 1.0 if product.resolution == match_data["resolution"] else 0.0
            score_components.append((res_match, 0.10))

        # Refresh rate match (10%)
        if product.refresh_rate and match_data["refresh_rate"]:
            rate_match = 1.0 if product.refresh_rate == match_data["refresh_rate"] else 0.0
            score_components.append((rate_match, 0.10))

        # Panel type match (5%)
        if product.panel_type and match_data["panel_type"]:
            panel_match = 1.0 if product.panel_type == match_data["panel_type"] else 0.0
            score_components.append((panel_match, 0.05))

        # Calculate weighted score
        if not score_components:
            return 0.0

        weighted_score = sum(score * weight for score, weight in score_components)
        total_weight = sum(weight for _, weight in score_components)

        return weighted_score / total_weight