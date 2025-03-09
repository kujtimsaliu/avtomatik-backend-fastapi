from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from starlette.background import BackgroundTask
import urllib.parse

from database import SessionLocal
from models import Product, Store, Pricing

app = FastAPI(title="Monitor Price Comparison API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)


# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic models for API responses
class StoreModel(BaseModel):
    id: str
    name: str
    website: str

    class Config:
        orm_mode = True


class PricingModel(BaseModel):
    id: str
    price: float
    stock_status: Optional[str]
    url: str
    last_updated: Optional[str]
    store: StoreModel

    class Config:
        orm_mode = True


class ProductSpecsModel(BaseModel):
    size: Optional[float]
    resolution: Optional[str]
    refresh_rate: Optional[float]
    panel_type: Optional[str]
    curved: Optional[bool]
    gaming: Optional[bool]
    hdr: Optional[bool]
    freesync: Optional[bool]
    gsync: Optional[bool]
    usb_c: Optional[bool]
    hdmi: Optional[bool]
    displayport: Optional[bool]
    speakers: Optional[bool]
    height_adjustable: Optional[bool]

    class Config:
        orm_mode = True


class ProductModel(BaseModel):
    id: str
    name: str
    brand: str
    model: str
    category: str
    specs: Optional[Dict[str, Any]]
    size: Optional[float]
    resolution: Optional[str]
    refresh_rate: Optional[float]
    panel_type: Optional[str]
    image_url: Optional[str]
    prices: List[PricingModel]

    class Config:
        orm_mode = True


class ProductComparisonModel(BaseModel):
    product: ProductModel
    best_price: Optional[PricingModel]
    price_difference: Optional[float]

    class Config:
        orm_mode = True


@app.get("/", tags=["Health"])
def read_root():
    return {"message": "Monitor Price Comparison API is running"}


@app.get("/products/", response_model=List[ProductModel], tags=["Products"])
def get_products(
        db: Session = Depends(get_db),
        skip: int = 0,
        limit: int = 100,
        brand: Optional[str] = None,
        min_size: Optional[float] = None,
        max_size: Optional[float] = None,
        min_refresh_rate: Optional[float] = None,
        panel_type: Optional[str] = None,
        resolution: Optional[str] = None,
        in_stock: Optional[bool] = None,
):
    """
    Get a list of products with optional filtering
    """
    query = db.query(Product)

    # Apply filters
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    if min_size:
        query = query.filter(Product.size >= min_size)
    if max_size:
        query = query.filter(Product.size <= max_size)
    if min_refresh_rate:
        query = query.filter(Product.refresh_rate >= min_refresh_rate)
    if panel_type:
        query = query.filter(Product.panel_type.ilike(f"%{panel_type}%"))
    if resolution:
        query = query.filter(Product.resolution == resolution)

    # Get products with pagination
    products = query.offset(skip).limit(limit).all()

    # Process results
    result = []
    for product in products:
        # Get all pricing for this product
        pricing_query = db.query(Pricing).filter(Pricing.product_id == product.id)

        # Apply in_stock filter if requested
        if in_stock:
            pricing_query = pricing_query.filter(Pricing.stock_status.ilike("%in stock%"))

        pricing_list = pricing_query.all()

        # Skip products with no pricing if in_stock filter is applied
        if in_stock and not pricing_list:
            continue

        # Create a product model with pricing information
        product_dict = {
            "id": product.id,
            "name": product.name,
            "brand": product.brand,
            "model": product.model,
            "category": product.category,
            "specs": product.specs,
            "size": product.size,
            "resolution": product.resolution,
            "refresh_rate": product.refresh_rate,
            "panel_type": product.panel_type,
            "image_url": product.image_url,
            "prices": []
        }

        # Add pricing information
        for pricing in pricing_list:
            store = db.query(Store).filter(Store.id == pricing.store_id).first()
            pricing_dict = {
                "id": pricing.id,
                "price": pricing.price,
                "stock_status": pricing.stock_status,
                "url": pricing.url,
                "last_updated": pricing.last_updated.isoformat() if pricing.last_updated else None,
                "store": {
                    "id": store.id,
                    "name": store.name,
                    "website": store.website
                }
            }
            product_dict["prices"].append(pricing_dict)

        result.append(product_dict)

    return result


@app.get("/products/{product_id}", response_model=ProductModel, tags=["Products"])
def get_product(product_id: str, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific product
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Get all pricing for this product
    pricing_list = db.query(Pricing).filter(Pricing.product_id == product.id).all()

    # Create a product model with pricing information
    product_dict = {
        "id": product.id,
        "name": product.name,
        "brand": product.brand,
        "model": product.model,
        "category": product.category,
        "specs": product.specs,
        "size": product.size,
        "resolution": product.resolution,
        "refresh_rate": product.refresh_rate,
        "panel_type": product.panel_type,
        "image_url": product.image_url,
        "prices": []
    }

    # Add pricing information
    for pricing in pricing_list:
        store = db.query(Store).filter(Store.id == pricing.store_id).first()
        pricing_dict = {
            "id": pricing.id,
            "price": pricing.price,
            "stock_status": pricing.stock_status,
            "url": pricing.url,
            "last_updated": pricing.last_updated.isoformat() if pricing.last_updated else None,
            "store": {
                "id": store.id,
                "name": store.name,
                "website": store.website
            }
        }
        product_dict["prices"].append(pricing_dict)

    return product_dict


@app.get("/compare/{product_id}", response_model=ProductComparisonModel, tags=["Comparison"])
def compare_product_prices(product_id: str, db: Session = Depends(get_db)):
    """
    Compare prices for a specific product across different stores
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Get all pricing for this product
    pricing_list = db.query(Pricing).filter(Pricing.product_id == product.id).all()

    if not pricing_list:
        raise HTTPException(status_code=404, detail="No pricing information found for this product")

    # Create a product model with pricing information
    product_dict = {
        "id": product.id,
        "name": product.name,
        "brand": product.brand,
        "model": product.model,
        "category": product.category,
        "specs": product.specs,
        "size": product.size,
        "resolution": product.resolution,
        "refresh_rate": product.refresh_rate,
        "panel_type": product.panel_type,
        "image_url": product.image_url,
        "prices": []
    }

    # Find the best (lowest) price
    best_price = None
    min_price = float('inf')

    # Process pricing information
    for pricing in pricing_list:
        store = db.query(Store).filter(Store.id == pricing.store_id).first()
        pricing_dict = {
            "id": pricing.id,
            "price": pricing.price,
            "stock_status": pricing.stock_status,
            "url": pricing.url,
            "last_updated": pricing.last_updated.isoformat() if pricing.last_updated else None,
            "store": {
                "id": store.id,
                "name": store.name,
                "website": store.website
            }
        }
        product_dict["prices"].append(pricing_dict)

        # Update best price if this is lower
        if pricing.price < min_price and pricing.stock_status and "in stock" in pricing.stock_status.lower():
            min_price = pricing.price
            best_price = pricing_dict

    # Calculate price difference (max - min)
    max_price = max(p.price for p in pricing_list)
    price_difference = max_price - min_price if min_price != float('inf') else 0

    return {
        "product": product_dict,
        "best_price": best_price,
        "price_difference": price_difference
    }


@app.get("/brands/", response_model=List[str], tags=["Filters"])
def get_brands(db: Session = Depends(get_db)):
    """
    Get a list of all available brands
    """
    brands = db.query(Product.brand).distinct().all()
    return [brand[0] for brand in brands]


@app.get("/stores/", response_model=List[StoreModel], tags=["Filters"])
def get_stores(db: Session = Depends(get_db)):
    """
    Get a list of all available stores
    """
    stores = db.query(Store).all()
    return stores


@app.get("/search/", response_model=List[ProductModel], tags=["Search"])
def search_products(
        query: str,
        db: Session = Depends(get_db),
        limit: int = 10
):
    """
    Search for products by name, brand, or model
    """
    search_term = f"%{query}%"
    products = db.query(Product).filter(
        (Product.name.ilike(search_term)) |
        (Product.brand.ilike(search_term)) |
        (Product.model.ilike(search_term))
    ).limit(limit).all()

    # Process results
    result = []
    for product in products:
        # Get all pricing for this product
        pricing_list = db.query(Pricing).filter(Pricing.product_id == product.id).all()

        # Create a product model with pricing information
        product_dict = {
            "id": product.id,
            "name": product.name,
            "brand": product.brand,
            "model": product.model,
            "category": product.category,
            "specs": product.specs,
            "size": product.size,
            "resolution": product.resolution,
            "refresh_rate": product.refresh_rate,
            "panel_type": product.panel_type,
            "image_url": product.image_url,
            "prices": []
        }

        # Add pricing information
        for pricing in pricing_list:
            store = db.query(Store).filter(Store.id == pricing.store_id).first()
            pricing_dict = {
                "id": pricing.id,
                "price": pricing.price,
                "stock_status": pricing.stock_status,
                "url": pricing.url,
                "last_updated": pricing.last_updated.isoformat() if pricing.last_updated else None,
                "store": {
                    "id": store.id,
                    "name": store.name,
                    "website": store.website
                }
            }
            product_dict["prices"].append(pricing_dict)

        result.append(product_dict)

    return result


@app.get("/products/multi-store/", response_model=List[ProductModel], tags=["Products"])
def get_multi_store_products(
        db: Session = Depends(get_db),
        min_stores: int = Query(2, description="Minimum number of stores selling the product"),
        skip: int = 0,
        limit: int = 100
):
    """
    Get products that are available in multiple stores (for price comparison)
    """
    # Find product IDs with multiple stores
    subquery = db.query(Pricing.product_id, func.count(Pricing.store_id).label("store_count")) \
        .group_by(Pricing.product_id) \
        .having(func.count(Pricing.store_id) >= min_stores) \
        .subquery()

    # Get the actual products
    products_query = db.query(Product) \
        .join(subquery, Product.id == subquery.c.product_id) \
        .order_by(subquery.c.store_count.desc()) \
        .offset(skip) \
        .limit(limit)

    products = products_query.all()

    # Process results
    result = []
    for product in products:
        # Get all pricing for this product
        pricing_list = db.query(Pricing).filter(Pricing.product_id == product.id).all()

        # Create a product model with pricing information
        product_dict = {
            "id": product.id,
            "name": product.name,
            "brand": product.brand,
            "model": product.model,
            "category": product.category,
            "specs": product.specs,
            "size": product.size,
            "resolution": product.resolution,
            "refresh_rate": product.refresh_rate,
            "panel_type": product.panel_type,
            "image_url": product.image_url,
            "prices": []
        }

        # Add pricing information
        for pricing in pricing_list:
            store = db.query(Store).filter(Store.id == pricing.store_id).first()
            pricing_dict = {
                "id": pricing.id,
                "price": pricing.price,
                "stock_status": pricing.stock_status,
                "url": pricing.url,
                "last_updated": pricing.last_updated.isoformat() if pricing.last_updated else None,
                "store": {
                    "id": store.id,
                    "name": store.name,
                    "website": store.website
                }
            }
            product_dict["prices"].append(pricing_dict)

        result.append(product_dict)

    return result


@app.get("/stats/", tags=["Statistics"])
def get_stats(db: Session = Depends(get_db)):
    """
    Get general statistics about the database
    """
    # Count total products
    product_count = db.query(Product).count()

    # Count products by brand
    brand_counts = db.query(Product.brand, func.count(Product.id)) \
        .group_by(Product.brand) \
        .order_by(func.count(Product.id).desc()) \
        .all()

    brand_stats = {brand: count for brand, count in brand_counts}

    # Count products by store
    from sqlalchemy import func
    store_counts = db.query(Store.name, func.count(Pricing.id)) \
        .join(Pricing, Store.id == Pricing.store_id) \
        .group_by(Store.name) \
        .all()

    store_stats = {store: count for store, count in store_counts}

    # Count products with multiple stores
    multi_store_products = db.query(Product.id) \
        .join(Pricing, Product.id == Pricing.product_id) \
        .group_by(Product.id) \
        .having(func.count(Pricing.store_id) > 1) \
        .count()

    # Get price range statistics
    price_stats = db.query(
        func.min(Pricing.price),
        func.avg(Pricing.price),
        func.max(Pricing.price)
    ).first()

    return {
        "total_products": product_count,
        "products_by_brand": brand_stats,
        "products_by_store": store_stats,
        "products_in_multiple_stores": multi_store_products,
        "price_statistics": {
            "min_price": price_stats[0],
            "avg_price": price_stats[1],
            "max_price": price_stats[2]
        }
    }


@app.get("/proxy-image/")
async def proxy_image(url: str):
    """
    Proxy an image from any URL through the backend to avoid CORS issues.
    Usage: /proxy-image/?url=https://www.anhoch.com/storage/media/image.jpg
    """
    try:
        # URL decode the parameter
        decoded_url = urllib.parse.unquote(url)

        # Use httpx to get the image
        async with httpx.AsyncClient() as client:
            response = await client.get(decoded_url)

            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch image")

            # Get the content type or default to image/jpeg
            content_type = response.headers.get("content-type", "image/jpeg")

            # Return the image data with the correct content type
            return Response(
                content=response.content,
                media_type=content_type,
                background=BackgroundTask(response.aclose)
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error proxying image: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)