import json
import logging
from typing import Dict, Any
import os

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal, engine, Base
from models import Product, Store, Pricing
from product_matcher import ProductMatcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_json_file(file_path: str) -> Dict[str, Any]:
    """Load JSON data from a file."""
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return {}

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            logger.info(f"Successfully loaded JSON file: {file_path}")
            return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in file {file_path}: {e}")
    except Exception as e:
        logger.error(f"Error loading JSON file {file_path}: {e}")

    return {}


def process_data():
    """Process the scraped data and populate the database."""
    # Create database tables if they don't exist
    Base.metadata.create_all(bind=engine)

    # Create a database session
    db = SessionLocal()

    try:
        # Initialize product matcher
        matcher = ProductMatcher(db)

        # Load data from JSON files
        logger.info("Loading Anhoch data...")
        anhoch_data = load_json_file('anhoch_products_2025-03-09T02-32-33-008Z.json')

        logger.info("Loading Neptun data...")
        neptun_data = load_json_file('neptun_products_2025-03-09T02-30-07-655Z.json')

        # Process Anhoch data
        logger.info("Processing Anhoch products...")
        anhoch_products = matcher.process_anhoch_data(anhoch_data)
        logger.info(f"Processed {len(anhoch_products)} Anhoch products")

        # Process Neptun data
        logger.info("Processing Neptun products...")
        neptun_products = matcher.process_neptun_data(neptun_data)
        logger.info(f"Processed {len(neptun_products)} Neptun products")

        # Save products to database
        logger.info("Saving products to database...")

        for product_data in anhoch_products:
            product, pricing = matcher.save_product(product_data)
            logger.debug(f"Saved Anhoch product: {product.brand} {product.model}")

        for product_data in neptun_products:
            product, pricing = matcher.save_product(product_data)
            logger.debug(f"Saved Neptun product: {product.brand} {product.model}")

        # Find matches between products
        logger.info("Finding product matches...")
        matches = matcher.find_product_matches()
        logger.info(f"Found {len(matches)} product matches")

        # Print match details
        if matches:
            for match in matches:
                logger.info(
                    f"Matched: {match['product'].brand} {match['product'].model} in {match['store'].name} (score: {match['score']:.2f})")

        logger.info("Data processing completed successfully")

    except Exception as e:
        logger.error(f"Error processing data: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def analyze_database_stats():
    """Analyze and print statistics about the database."""
    db = SessionLocal()

    try:
        # Count total products
        product_count = db.query(Product).count()
        logger.info(f"Total unique products: {product_count}")

        # Count products by brand
        brand_counts = db.query(Product.brand, func.count(Product.id)) \
            .group_by(Product.brand) \
            .order_by(func.count(Product.id).desc()) \
            .all()

        logger.info("Products by brand:")
        for brand, count in brand_counts:
            logger.info(f"  {brand}: {count}")

        # Count products by store
        store_counts = db.query(Store.name, func.count(Pricing.id)) \
            .join(Pricing, Store.id == Pricing.store_id) \
            .group_by(Store.name) \
            .all()

        logger.info("Products by store:")
        for store, count in store_counts:
            logger.info(f"  {store}: {count}")

        # Count products with multiple stores
        multi_store_products = db.query(Product.id, func.count(Pricing.store_id)) \
            .join(Pricing, Product.id == Pricing.product_id) \
            .group_by(Product.id) \
            .having(func.count(Pricing.store_id) > 1) \
            .count()

        logger.info(f"Products available in multiple stores: {multi_store_products}")

    except Exception as e:
        logger.error(f"Error analyzing database: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    process_data()
    analyze_database_stats()