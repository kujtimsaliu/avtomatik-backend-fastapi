from sqlalchemy import Column, String, Float, DateTime, ForeignKey, JSON, Text, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import uuid

from database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    brand = Column(String(100), nullable=False, index=True)
    model = Column(String(100), nullable=False, index=True)
    category = Column(String(100), nullable=False)
    specs = Column(JSON, nullable=True)  # Store specs as JSON for flexibility
    size = Column(Float, nullable=True)  # Display size in inches
    resolution = Column(String(50), nullable=True)  # e.g., "1920x1080", "2560x1440"
    refresh_rate = Column(Float, nullable=True)  # e.g., 60, 75, 144, 165
    panel_type = Column(String(20), nullable=True)  # e.g., "IPS", "VA", "TN"
    image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship with Pricing
    pricing = relationship("Pricing", back_populates="product")

    def __repr__(self):
        return f"<Product(name='{self.name}', brand='{self.brand}', model='{self.model}')>"


class Store(Base):
    __tablename__ = "stores"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    website = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=func.now())

    # Relationship with Pricing
    pricing = relationship("Pricing", back_populates="store")

    def __repr__(self):
        return f"<Store(name='{self.name}', website='{self.website}')>"


class Pricing(Base):
    __tablename__ = "pricing"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    store_id = Column(String(36), ForeignKey("stores.id"), nullable=False)
    price = Column(Float, nullable=False)  # Store price in MKD
    stock_status = Column(String(50), nullable=True)  # e.g., "In Stock", "Out of Stock", "Unknown"
    url = Column(String(500), nullable=False)  # URL to the product page
    original_name = Column(Text, nullable=True)  # Original product name from store
    original_json = Column(JSON, nullable=True)  # Original JSON data for reference
    last_updated = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    product = relationship("Product", back_populates="pricing")
    store = relationship("Store", back_populates="pricing")

    def __repr__(self):
        return f"<Pricing(product_id='{self.product_id}', store_id='{self.store_id}', price={self.price})>"