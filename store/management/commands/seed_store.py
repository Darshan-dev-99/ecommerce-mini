"""Seed the store with a realistic India-first catalogue.

Usage:
    python manage.py seed_store            # create what is missing
    python manage.py seed_store --flush    # wipe demo data first

Everything is idempotent: running it twice does not duplicate rows.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from store.models import (
    Address,
    Brand,
    Cart,
    CartItem,
    Category,
    Coupon,
    Order,
    OrderEvent,
    OrderItem,
    Pincode,
    Product,
    ProductImage,
    RecentlyViewed,
    ReturnRequest,
    Review,
    Role,
    User,
    WishlistItem,
)
from store.services import BILLING_FIELDS, quote

IMG = "https://images.unsplash.com/photo-{0}?auto=format&fit=crop&w=900&q=75"

CATEGORIES = [
    ("Mobiles", "📱", 1, "Smartphones from every leading brand"),
    ("Electronics", "🎧", 2, "Audio, wearables, TVs and cameras"),
    ("Computers", "💻", 3, "Laptops, tablets and gaming gear"),
    ("Men's Fashion", "👕", 4, "Shirts, jeans and everyday essentials"),
    ("Women's Fashion", "👗", 5, "Kurtas, sarees and modern ethnic wear"),
    ("Footwear", "👟", 6, "Running shoes, sneakers and formals"),
    ("Beauty", "💄", 7, "Skincare, make-up and personal care"),
    ("Home & Kitchen", "🍳", 8, "Cookware, dinnerware and storage"),
    ("Grocery", "🛒", 9, "Daily staples delivered to your door"),
    ("Sports & Fitness", "🏏", 10, "Cricket, badminton and home gym"),
    ("Appliances", "🧺", 11, "Refrigerators, washers and more"),
    ("Books & Toys", "📚", 12, "Bestsellers and family games"),
]

BRANDS = [
    ("Samsung", "Do what you can't"),
    ("Apple", "Think different"),
    ("OnePlus", "Never settle"),
    ("Xiaomi", "Innovation for everyone"),
    ("Realme", "Dare to leap"),
    ("Vivo", "Joy of humanity"),
    ("boAt", "Plug into nirvana"),
    ("Sony", "Make believe"),
    ("JBL", "Hear the truth"),
    ("Noise", "Made for the go-getters"),
    ("HP", "Keep reinventing"),
    ("Lenovo", "Smarter technology for all"),
    ("ASUS", "In search of incredible"),
    ("Levi's", "Quality never goes out of style"),
    ("Allen Solly", "Friday dressing"),
    ("U.S. Polo Assn.", "Authentic American style"),
    ("Fastrack", "Move on"),
    ("Ray-Ban", "Never hide"),
    ("Libas", "Ethnic wear, everyday"),
    ("FabIndia", "Celebrating Indian craft"),
    ("BIBA", "Change is beautiful"),
    ("Mamaearth", "Goodness inside"),
    ("Lakmé", "India's beauty expert"),
    ("Nivea", "Care for skin"),
    ("Nike", "Just do it"),
    ("Adidas", "Impossible is nothing"),
    ("Puma", "Forever faster"),
    ("Bata", "A step ahead"),
    ("Woodland", "Outdoor specialists"),
    ("Prestige", "Jo biwi se kare pyaar"),
    ("Hawkins", "Cook smart"),
    ("Philips", "Sense and simplicity"),
    ("Milton", "Life is a picnic"),
    ("Cello", "Ideas for life"),
    ("Tata Tea", "Jaago re"),
    ("Amul", "The taste of India"),
    ("India Gate", "Chef's choice"),
    ("Haldiram's", "Taste of tradition"),
    ("SG", "Play with confidence"),
    ("Boldfit", "Fitness for everyone"),
    ("Yonex", "The only way to win"),
    ("LG", "Life's good"),
    ("Funskool", "Learn through play"),
    ("Penguin", "Books for every reader"),
    ("Canon", "Delighting you always"),
]

# name, brand, category, mrp, price, stock, image id, rating, ratings, sold,
# badge, specs, description, delivery_days, warranty
PRODUCTS = [
    (
        "Samsung Galaxy S24 5G (Cobalt Violet, 256 GB)", "Samsung", "Mobiles",
        79999, 64999, 18, "1511707171634-5f897ff02aa9", 4.5, 3821, 2140, "Bestseller",
        ["6.2 inch FHD+ Dynamic AMOLED 2X, 120 Hz", "Exynos 2400 with Galaxy AI",
         "50 MP triple camera, 3x optical zoom", "256 GB storage with 8 GB RAM"],
        "Flagship Galaxy experience with AI translation, night photography and 7 years of updates.",
        1, "1 Year Manufacturer Warranty",
    ),
    (
        "Apple iPhone 15 (Blue, 128 GB)", "Apple", "Mobiles",
        79900, 69900, 11, "1592750475338-74b7b21085ab", 4.6, 5124, 1780, "Top Rated",
        ["6.1 inch Super Retina XDR display", "A16 Bionic chip with 48 MP main camera",
         "USB-C with 20 W fast charging", "Dynamic Island and Crash Detection"],
        "The iPhone 15 brings a 48 MP camera, Dynamic Island and USB-C in a durable colour-infused glass body.",
        2, "1 Year Apple Care Warranty",
    ),
    (
        "OnePlus 12R (Cool Blue, 256 GB)", "OnePlus", "Mobiles",
        45999, 39999, 24, "1616348436168-de43ad0db179", 4.4, 2118, 960, "Hot Deal",
        ["6.78 inch 1.5K ProXDR display, 120 Hz", "Snapdragon 8 Gen 2",
         "100 W SUPERVOOC charging", "5500 mAh with 50 MP Sony sensor"],
        "Flagship power at a mid-range price with 100 W charging that tops up in 26 minutes.",
        2, "1 Year Manufacturer Warranty",
    ),
    (
        "Redmi Note 13 Pro 5G (Midnight Black, 128 GB)", "Xiaomi", "Mobiles",
        27999, 23999, 40, "1592899677977-9c10ca588bbd", 4.3, 41230, 6320, "Best Seller",
        ["6.67 inch 1.5K AMOLED, 120 Hz", "200 MP OIS camera",
         "67 W turbo charging", "IP54 rated with Gorilla Glass Victus"],
        "The 200 MP camera and 120 Hz AMOLED make this India's favourite sub-25k 5G phone.",
        1, "1 Year Manufacturer Warranty",
    ),
    (
        "realme narzo 70 Turbo 5G (Racing Green, 128 GB)", "Realme", "Mobiles",
        21999, 17999, 0, "1567581935884-3349723552ca", 4.1, 1830, 2410, "Budget Pick",
        ["6.67 inch 120 Hz AMOLED", "MediaTek Dimensity 7300",
         "5000 mAh, 45 W charging", "IP65 water resistance"],
        "Performance-first 5G phone for gamers on a budget.",
        2, "1 Year Manufacturer Warranty",
    ),
    (
        "vivo T3 5G (Crystal Flake, 128 GB)", "Vivo", "Mobiles",
        24999, 19999, 32, "1598327105666-5b89351aff97", 4.2, 3920, 3100, "",
        ["6.67 inch AMOLED, 120 Hz", "MediaTek Dimensity 7200",
         "5000 mAh with 44 W FlashCharge", "Sony IMX882 OIS camera"],
        "Slim 5G phone with a bright AMOLED screen and dependable battery life.",
        2, "1 Year Manufacturer Warranty",
    ),
    (
        "boAt Rockerz 450 Bluetooth Headphone", "boAt", "Electronics",
        2990, 1299, 120, "1505740420928-5e560c06d30e", 4.2, 89210, 45210, "Deal of the Day",
        ["Up to 15 hours playback", "40 mm dynamic drivers",
         "Padded ear cushions", "Dual pairing with voice assistant"],
        "India's most popular budget headphone - punchy bass and all-day comfort.",
        3, "1 Year Warranty",
    ),
    (
        "Sony WH-CH720N Noise Cancelling Headphones", "Sony", "Electronics",
        14990, 9999, 26, "1583394838336-acd977736f90", 4.5, 6210, 1980, "",
        ["Dual noise sensor technology", "Up to 35 hours battery",
         "Multipoint connection", "Lightweight 192 g design"],
        "Wireless noise cancellation tuned for Indian commutes, with 35 hours of battery.",
        2, "1 Year Sony India Warranty",
    ),
    (
        "JBL Flip 6 Portable Speaker", "JBL", "Electronics",
        11999, 8499, 19, "1608043152269-423dbba4e7e1", 4.6, 3410, 1240, "Top Rated",
        ["20 W output with racetrack driver", "IP67 waterproof and dustproof",
         "12 hours playtime", "PartyBoost pairing"],
        "Rugged portable speaker that survives the monsoon and the beach.",
        3, "1 Year JBL Warranty",
    ),
    (
        "Noise ColorFit Pro 5 Smartwatch", "Noise", "Electronics",
        6999, 3499, 64, "1523275335684-37898b6baf30", 4.1, 15320, 8210, "Bestseller",
        ["1.85 inch AMOLED always-on display", "Bluetooth calling",
         "100+ sports modes", "7 days battery life"],
        "Make every workout count with Bluetooth calling and a bright AMOLED display.",
        2, "1 Year Warranty",
    ),
    (
        "Mi 108 cm (43 inch) 4K LED Smart TV", "Xiaomi", "Electronics",
        34999, 24999, 14, "1593359677879-a4bb92f829d1", 4.3, 9210, 1620, "Festive Offer",
        ["4K Dolby Vision display", "PatchWall with 30+ OTT apps",
         "Dolby Atmos 30 W speakers", "Google Assistant built-in"],
        "Cinema-scale entertainment with Dolby Vision and Atmos at a living-room price.",
        4, "1 Year Comprehensive Warranty",
    ),
    (
        "Canon EOS 1500D DSLR with 18-55 mm Lens", "Canon", "Electronics",
        49990, 42990, 7, "1516035069371-29a1b244cc32", 4.4, 1820, 410, "",
        ["24.1 MP APS-C sensor", "DIGIC 4+ processor",
         "Full HD video recording", "Wi-Fi with Canon app"],
        "The classic first DSLR for creators - sharp stills and easy sharing.",
        3, "2 Year Canon India Warranty",
    ),
    (
        "HP Pavilion 15 (Intel i5 12th Gen, 16 GB)", "HP", "Computers",
        78999, 62990, 9, "1496181133206-80ce9b88a853", 4.2, 2180, 640, "",
        ["12th Gen Intel Core i5", "16 GB DDR4, 512 GB SSD",
         "15.6 inch FHD IPS display", "Backlit keyboard with numeric pad"],
        "Balanced everyday laptop for students and work-from-home professionals.",
        3, "1 Year Onsite Warranty",
    ),
    (
        "Apple MacBook Air M2 (8 GB / 256 GB, Midnight)", "Apple", "Computers",
        114900, 99990, 6, "1611186871348-b1ce696e52c9", 4.8, 3410, 720, "Premium",
        ["Apple M2 chip with 8-core CPU", "13.6 inch Liquid Retina display",
         "18 hours battery life", "MagSafe charging, fanless design"],
        "Silent, feather-light and fast - the default choice for creators.",
        2, "1 Year Apple Warranty",
    ),
    (
        "Lenovo IdeaPad Slim 3 (Ryzen 5, 16 GB)", "Lenovo", "Computers",
        62990, 47990, 21, "1603302576837-37561b2e2302", 4.1, 1640, 980, "",
        ["AMD Ryzen 5 7520U", "16 GB LPDDR5 memory",
         "512 GB NVMe SSD", "15.6 inch FHD display, 1.62 kg"],
        "Value laptop with 16 GB memory and fast SSD storage for multitasking.",
        3, "1 Year Warranty",
    ),
    (
        "ASUS TUF Gaming F15 (RTX 3050, i5 11th Gen)", "ASUS", "Computers",
        89990, 74990, 8, "1603302576837-37561b2e2302", 4.4, 980, 310, "Gaming",
        ["NVIDIA GeForce RTX 3050 4 GB", "144 Hz FHD display",
         "Intel Core i5 11400H", "Self-cleaning cooling, MIL-STD durability"],
        "Entry gaming laptop engineered for Indian summers with upgraded thermals.",
        4, "1 Year Warranty",
    ),
    (
        "Samsung Galaxy Tab S9 FE (Wi-Fi, 128 GB)", "Samsung", "Computers",
        44999, 36999, 12, "1544244015-0df4b3ffc6b0", 4.3, 720, 260, "",
        ["10.9 inch TFT display, 90 Hz", "Exynos 1380",
         "S Pen included", "8000 mAh battery, IP68"],
        "Note-taking and streaming tablet with the S Pen in the box.",
        2, "1 Year Warranty",
    ),
    (
        "Allen Solly Men Slim Fit Cotton Shirt", "Allen Solly", "Men's Fashion",
        2499, 1099, 55, "1596755094514-f87e34085b2c", 4.0, 4210, 3120, "",
        ["100% cotton, slim fit", "Full sleeves with button-down collar",
         "Machine washable", "Available in 6 colours"],
        "Office-ready cotton shirt that survives Indian summers.",
        4, "30 Day Return",
    ),
    (
        "Levi's Men 511 Slim Fit Jeans", "Levi's", "Men's Fashion",
        3999, 2399, 38, "1542272604-787c3835535d", 4.3, 6210, 2150, "Bestseller",
        ["Slim fit with stretch denim", "5-pocket styling",
         "Mid rise, tapered leg", "Authentic Levi's hardware"],
        "The 511 is Levi's best-selling slim fit - stretch denim, all-day comfort.",
        5, "30 Day Return",
    ),
    (
        "U.S. Polo Assn. Men Solid Polo T-Shirt", "U.S. Polo Assn.", "Men's Fashion",
        1799, 899, 72, "1521572163474-6864f9cf17ab", 4.1, 3100, 4210, "",
        ["100% combed cotton pique", "Ribbed collar and cuffs",
         "Signature embroidered logo", "Regular fit"],
        "A weekend classic that pairs with everything in the wardrobe.",
        4, "30 Day Return",
    ),
    (
        "Fastrack Men Analogue Watch", "Fastrack", "Men's Fashion",
        3495, 1999, 44, "1524592094714-0f0654e20314", 4.2, 8120, 5320, "",
        ["Stainless steel case", "Water resistant to 30 m",
         "2 year warranty", "Leather strap"],
        "Everyday analogue watch with a clean dial and durable strap.",
        3, "2 Year Warranty",
    ),
    (
        "Ray-Ban Aviator Sunglasses", "Ray-Ban", "Men's Fashion",
        8990, 6490, 15, "1511499767150-a48a237f0083", 4.6, 1520, 380, "Premium",
        ["G-15 green lenses, 100% UV protection", "Lightweight metal frame",
         "Iconic teardrop shape", "Includes case and cloth"],
        "The original aviator - timeless, unisex and unmistakable.",
        3, "2 Year Warranty",
    ),
    (
        "Libas Women Printed A-Line Kurta", "Libas", "Women's Fashion",
        2499, 999, 60, "1594633312681-425c7b97ccd1", 4.2, 9120, 6210, "Bestseller",
        ["Rayon fabric with block print", "A-line silhouette with 3/4 sleeves",
         "Side pockets", "Machine washable"],
        "Breathable everyday kurta that works from desk to dinner.",
        4, "30 Day Return",
    ),
    (
        "FabIndia Cotton Handblock Saree", "FabIndia", "Women's Fashion",
        4999, 3499, 22, "1610030469983-98e550d6193c", 4.5, 890, 210, "Handcrafted",
        ["Handblock printed cotton", "5.5 m saree with blouse piece",
         "Natural dyes", "Made by artisan clusters"],
        "Handcrafted saree celebrating traditional Indian block printing.",
        5, "15 Day Return",
    ),
    (
        "BIBA Women Anarkali Kurta Set", "BIBA", "Women's Fashion",
        3999, 1999, 31, "1583391733956-3750e0ff4e8b", 4.3, 2310, 1420, "",
        ["Georgette anarkali with dupatta", "Embroidered yoke",
         "Comes with churidar", "Dry clean only"],
        "Wedding-season ready anarkali set at a high-street price.",
        5, "15 Day Return",
    ),
    (
        "Mamaearth Vitamin C Face Serum 30 ml", "Mamaearth", "Beauty",
        599, 349, 90, "1556228578-8c89e6adf883", 4.1, 21300, 18210, "Bestseller",
        ["Vitamin C from orange extract", "Turmeric for glow",
         "Dermatologically tested", "Suitable for all skin types"],
        "Daily glow serum with vitamin C and turmeric, free from parabens.",
        3, "6 Month Return",
    ),
    (
        "Lakmé Absolute Matte Lipstick", "Lakmé", "Beauty",
        750, 525, 76, "1586495777744-4413f21062fa", 4.2, 5120, 3120, "",
        ["Intense matte finish", "8 hour transfer-proof wear",
         "Enriched with argan oil", "12 shades"],
        "Weightless matte lipstick that stays through chai and meetings.",
        3, "15 Day Return",
    ),
    (
        "Nivea Soft Moisturising Cream 200 ml", "Nivea", "Beauty",
        599, 449, 100, "1556228578-8c89e6adf883", 4.4, 9120, 7210, "",
        ["Jojoba oil and vitamin E", "Non-greasy, fast absorbing",
         "For face, hands and body", "Dermatologically approved"],
        "All-purpose moisturiser for Indian winters and air-conditioned offices.",
        3, "6 Month Return",
    ),
    (
        "Nike Revolution 7 Running Shoes", "Nike", "Footwear",
        4495, 3149, 45, "1542291026-7eec264c27ff", 4.3, 6210, 3210, "Bestseller",
        ["Breathable mesh upper", "Soft foam midsole",
         "Rubber outsole with traction pattern", "Unisex sizing"],
        "Everyday running shoe with a cushioned ride for road and treadmill.",
        4, "30 Day Return",
    ),
    (
        "Adidas Ultraboost Light Running Shoes", "Adidas", "Footwear",
        19999, 13999, 12, "1608231387042-66d1773070a5", 4.6, 1820, 410, "Premium",
        ["Light BOOST midsole", "Primeknit+ upper",
         "Continental rubber outsole", "Linear Energy Push system"],
        "30% lighter BOOST foam for long-distance comfort.",
        4, "30 Day Return",
    ),
    (
        "Puma Smashic Unisex Sneakers", "Puma", "Footwear",
        3999, 2399, 52, "1600185365483-26d7a4cc7519", 4.2, 7210, 4120, "",
        ["SoftFoam+ sockliner", "Canvas and suede upper",
         "Rubber cupsole", "Everyday street style"],
        "Retro court sneaker that works with jeans and joggers alike.",
        4, "30 Day Return",
    ),
    (
        "Bata Men Formal Derby Shoes", "Bata", "Footwear",
        2499, 1499, 38, "1460353581641-37baddab0fa2", 4.0, 3120, 1820, "",
        ["Genuine leather upper", "Cushioned insole",
         "Slip-resistant sole", "Office formal"],
        "Comfortable formal shoe for long working days.",
        5, "30 Day Return",
    ),
    (
        "Woodland Men Leather Trekking Shoes", "Woodland", "Footwear",
        4995, 3495, 26, "1606107557195-0e29a4b5b4aa", 4.5, 4120, 1120, "",
        ["Nubuck leather upper", "High-traction rubber sole",
         "Padded ankle collar", "Water resistant"],
        "Built for Himalayan trails and Indian monsoon streets.",
        5, "3 Month Return",
    ),
    (
        "Prestige Omega Deluxe Non-Stick Cookware Set", "Prestige", "Home & Kitchen",
        5995, 2999, 30, "1556909212-d5b604d0c90d", 4.3, 8120, 3210, "Combo",
        ["4 piece non-stick set", "3-layer PFOA-free coating",
         "Gas and induction compatible", "Cool-touch bakelite handles"],
        "Kadhai, tawa, dosa tawa and lid - the starter kit for every kitchen.",
        4, "1 Year Warranty",
    ),
    (
        "Hawkins Contura 3 L Pressure Cooker", "Hawkins", "Home & Kitchen",
        2450, 1899, 42, "1585515320310-259814833e62", 4.5, 15210, 8210, "Bestseller",
        ["3 litre aluminium body", "Contura shape for easy stirring",
         "Precision safety valve", "5 year warranty"],
        "The pressure cooker most Indian kitchens grow up with.",
        3, "5 Year Warranty",
    ),
    (
        "Philips HL7756 Mixer Grinder 750 W", "Philips", "Home & Kitchen",
        4995, 3299, 27, "1585237017125-24baf8d7406f", 4.3, 9120, 4210, "",
        ["750 W Turbo motor", "3 jars + spatula",
         "Advanced air ventilation", "2 year motor warranty"],
        "Powerful mixer grinder for idli batter, chutney and dry masala.",
        3, "2 Year Warranty",
    ),
    (
        "Milton Thermosteel Flip Lid Flask 1 L", "Milton", "Home & Kitchen",
        1899, 1299, 68, "1602143407151-7111542de6e8", 4.4, 6210, 5120, "",
        ["24 hours hot or cold", "18/8 stainless steel",
         "Leak-proof flip lid", "Food-grade, BPA free"],
        "Keeps chai hot through the longest meeting.",
        3, "1 Year Warranty",
    ),
    (
        "Cello Opalware Dinner Set 27 Pieces", "Cello", "Home & Kitchen",
        3999, 2299, 19, "1578500494198-246f612d3b3d", 4.2, 3120, 1420, "",
        ["27 piece opalware set", "Bone ash free, chip resistant",
         "Microwave and dishwasher safe", "Lightweight for daily use"],
        "Everyday dinner set that looks festive and survives the dishwasher.",
        4, "6 Month Warranty",
    ),
    (
        "Tata Tea Premium Leaf 1 kg", "Tata Tea", "Grocery",
        620, 565, 150, "1544787219-7f47ccb76574", 4.4, 25310, 30210, "Subscribe & Save",
        ["Rich Assam leaf blend", "Makes 400+ cups",
         "Zip-lock pack for freshness", "100% natural"],
        "The everyday chai that India brews by the litre.",
        2, "Best before 12 months",
    ),
    (
        "Amul Gold Full Cream Milk 1 L (Pack of 6)", "Amul", "Grocery",
        420, 399, 200, "1550583724-b2692b85b150", 4.6, 41210, 52110, "Daily Needs",
        ["6% fat full cream milk", "Tetra Pak, no preservatives",
         "6 x 1 litre packs", "Chilled delivery"],
        "Fresh full cream milk for tea, curd and desserts.",
        1, "Best before 6 months",
    ),
    (
        "India Gate Basmati Rice Classic 5 kg", "India Gate", "Grocery",
        899, 749, 120, "1586201375761-83865001e31c", 4.3, 18210, 22100, "",
        ["Aged long grain basmati", "Ideal for biryani and pulao",
         "5 kg vacuum pack", "Low broken grain percentage"],
        "Aged basmati that cooks long, fluffy grains every time.",
        2, "Best before 24 months",
    ),
    (
        "Haldiram's Nagpur Aloo Bhujia 1 kg", "Haldiram's", "Grocery",
        340, 299, 90, "1601050690597-df0568f70950", 4.2, 9120, 14210, "",
        ["Crispy potato and besan sev", "Authentic Nagpur recipe",
         "No added preservatives", "1 kg family pack"],
        "The snack that disappears before the guests arrive.",
        2, "Best before 6 months",
    ),
    (
        "SG RSD Spark Kashmir Willow Cricket Bat", "SG", "Sports & Fitness",
        2499, 1699, 33, "1531415074968-036ba1b575da", 4.3, 3120, 1820, "",
        ["Kashmir willow, full size", "Pre-fitted chevron grip",
         "Ideal for tennis ball cricket", "Weight 1100-1200 g"],
        "Ready-to-play bat for gully cricket and weekend tournaments.",
        3, "1 Month Warranty",
    ),
    (
        "Boldfit Hex Dumbbell 10 kg (Pair)", "Boldfit", "Sports & Fitness",
        3999, 2499, 24, "1517836357463-d25dfeac3438", 4.2, 5120, 2410, "Home Gym",
        ["Rubber coated hex heads", "Anti-roll design",
         "Knurled chrome handle", "2 x 10 kg"],
        "Build a home gym with hex dumbbells that protect your floor.",
        4, "6 Month Warranty",
    ),
    (
        "Yonex ZR 100 Light Badminton Racket", "Yonex", "Sports & Fitness",
        1990, 1290, 48, "1626224583764-f87db24ac4ea", 4.4, 2310, 1210, "",
        ["Lightweight aluminium frame", "Pre-strung at 20 lbs",
         "Comes with full cover", "For beginners and casual play"],
        "Light racket with a big sweet spot for weekend rallies.",
        3, "1 Month Warranty",
    ),
    (
        "LG 190 L 5 Star Single Door Refrigerator", "LG", "Appliances",
        21990, 17990, 7, "1571175443880-49e1d25b2bc5", 4.4, 4120, 1510, "Exchange Offer",
        ["Smart Inverter compressor", "5 star energy rating",
         "Base stand with drawer", "10 year compressor warranty"],
        "Energy-efficient fridge sized for Indian families.",
        5, "1 Year Comprehensive + 10 Year Compressor",
    ),
    (
        "Samsung 7 kg Fully Automatic Washing Machine", "Samsung", "Appliances",
        24990, 19990, 5, "1626806787461-102c1bfaaea1", 4.3, 3210, 1210, "",
        ["Diamond drum", "Centre jet pulsator",
         "Eco Tub Clean", "7 kg top load"],
        "Top-load washer with a drum that is gentle on sarees.",
        5, "2 Year Comprehensive + 10 Year Motor",
    ),
    (
        "Funskool Monopoly Board Game", "Funskool", "Books & Toys",
        999, 749, 40, "1559454403-b8fb88521f11", 4.5, 6210, 3120, "Family Pick",
        ["Classic Monopoly rules", "2-6 players, age 8+",
         "Includes property cards and tokens", "Great for family nights"],
        "The board game that starts arguments and friendships alike.",
        3, "15 Day Return",
    ),
    (
        "Atomic Habits by James Clear (Paperback)", "Penguin", "Books & Toys",
        799, 399, 85, "1512820790803-83ca734da794", 4.7, 32100, 41210, "Bestseller",
        ["Paperback, 320 pages", "International bestseller",
         "Practical habit-building framework", "Penguin Random House"],
        "Tiny changes, remarkable results - the most read productivity book of the decade.",
        2, "15 Day Return",
    ),
]

COUPONS = [
    ("WELCOME200", "Flat ₹200 off your first order above ₹999", Coupon.DiscountType.FLAT, 200, 999, 200, 0),
    ("BBD10", "10% instant discount up to ₹500", Coupon.DiscountType.PERCENT, 10, 1499, 500, 0),
    ("TECH1500", "₹1500 off laptops and phones above ₹15000", Coupon.DiscountType.FLAT, 1500, 15000, 1500, 300),
    ("FASHION20", "20% off fashion, up to ₹400", Coupon.DiscountType.PERCENT, 20, 999, 400, 0),
    ("BANK5", "5% HDFC bank offer up to ₹300", Coupon.DiscountType.PERCENT, 5, 999, 300, 0),
    ("GROCERY50", "₹50 off groceries above ₹499", Coupon.DiscountType.FLAT, 50, 499, 50, 0),
]

PINCODES = [
    ("560001", "Bengaluru", "Karnataka", 1, 2, True),
    ("560034", "Bengaluru", "Karnataka", 1, 3, True),
    ("110001", "New Delhi", "Delhi", 1, 3, True),
    ("400001", "Mumbai", "Maharashtra", 1, 2, True),
    ("400051", "Mumbai", "Maharashtra", 2, 3, True),
    ("600001", "Chennai", "Tamil Nadu", 2, 4, True),
    ("500001", "Hyderabad", "Telangana", 1, 3, True),
    ("700001", "Kolkata", "West Bengal", 2, 4, True),
    ("411001", "Pune", "Maharashtra", 2, 3, True),
    ("380001", "Ahmedabad", "Gujarat", 2, 4, True),
    ("302001", "Jaipur", "Rajasthan", 2, 5, True),
    ("226001", "Lucknow", "Uttar Pradesh", 3, 5, True),
    ("160017", "Chandigarh", "Chandigarh", 2, 4, True),
    ("682001", "Kochi", "Kerala", 3, 5, True),
    ("781001", "Guwahati", "Assam", 4, 6, False),
    ("440001", "Nagpur", "Maharashtra", 2, 4, True),
    ("751001", "Bhubaneswar", "Odisha", 3, 5, True),
    ("452001", "Indore", "Madhya Pradesh", 2, 4, True),
    ("248001", "Dehradun", "Uttarakhand", 3, 5, True),
    ("800001", "Patna", "Bihar", 3, 6, True),
    ("190001", "Srinagar", "Jammu & Kashmir", 5, 7, False, False),
]

REVIEW_SNIPPETS = [
    (5, "Worth every rupee", "Delivery was a day early and the packaging was pristine. Using it daily for two weeks with zero complaints."),
    (4, "Great value for money", "Does everything promised. Docking one star because the box was slightly dented on arrival."),
    (5, "Exactly as described", "Colour and finish match the photos. Flipkart-style packaging with the invoice inside."),
    (3, "Decent, not extraordinary", "Works fine for everyday use but the finish could be better at this price."),
    (4, "Fast delivery in Bengaluru", "Ordered on Monday, delivered Tuesday evening. Quality is solid for the price."),
    (5, "Bought during the sale", "Got a fantastic festive discount plus the bank offer. Highly recommended."),
    (4, "Good buy for gifting", "Bought this for my father and he loves it. Instructions could be clearer."),
    (2, "Okay product", "Arrived with a minor scratch. Return was easy and the pickup happened the next day."),
]

GALLERY = {
    "Mobiles": ["1511707171634-5f897ff02aa9", "1592750475338-74b7b21085ab", "1598327105666-5b89351aff97"],
    "Electronics": ["1505740420928-5e560c06d30e", "1608043152269-423dbba4e7e1", "1593359677879-a4bb92f829d1"],
    "Computers": ["1496181133206-80ce9b88a853", "1611186871348-b1ce696e52c9", "1544244015-0df4b3ffc6b0"],
    "Men's Fashion": ["1521572163474-6864f9cf17ab", "1542272604-787c3835535d", "1524592094714-0f0654e20314"],
    "Women's Fashion": ["1594633312681-425c7b97ccd1", "1610030469983-98e550d6193c", "1583391733956-3750e0ff4e8b"],
    "Footwear": ["1542291026-7eec264c27ff", "1600185365483-26d7a4cc7519", "1608231387042-66d1773070a5"],
    "Beauty": ["1556228578-8c89e6adf883", "1586495777744-4413f21062fa", "1541643600914-78b084683601"],
    "Home & Kitchen": ["1556909212-d5b604d0c90d", "1585515320310-259814833e62", "1585237017125-24baf8d7406f"],
    "Grocery": ["1542838132-92c53300491e", "1586201375761-83865001e31c", "1544787219-7f47ccb76574"],
    "Sports & Fitness": ["1531415074968-036ba1b575da", "1517836357463-d25dfeac3438", "1626224583764-f87db24ac4ea"],
    "Appliances": ["1571175443880-49e1d25b2bc5", "1626806787461-102c1bfaaea1", "1593359677879-a4bb92f829d1"],
    "Books & Toys": ["1512820790803-83ca734da794", "1559454403-b8fb88521f11", "1516035069371-29a1b244cc32"],
}

ADDRESS_BOOK = [
    ("Home", "403, Sunflower Residency", "12th Main, Indiranagar", "Bengaluru", "Karnataka", "560034"),
    ("Work", "Prestige Tech Park, Block C", "Outer Ring Road, Kadubeesanahalli", "Bengaluru", "Karnataka", "560001"),
]

PEOPLE = [
    ("priya", "Priya", "Sharma", "priya.sharma@example.in", "9812345670"),
    ("arjun", "Arjun", "Mehta", "arjun.mehta@example.in", "9822345671"),
    ("neha", "Neha", "Iyer", "neha.iyer@example.in", "9833345672"),
    ("rahul", "Rahul", "Verma", "rahul.verma@example.in", "9844345673"),
    ("kavya", "Kavya", "Reddy", "kavya.reddy@example.in", "9855345674"),
    ("vikram", "Vikram", "Singh", "vikram.singh@example.in", "9866345675"),
]

PIPELINE = [
    Order.Status.PLACED,
    Order.Status.PACKED,
    Order.Status.SHIPPED,
    Order.Status.OUT_FOR_DELIVERY,
    Order.Status.DELIVERED,
]

EVENT_NOTES = {
    Order.Status.PLACED: "Order confirmed and shared with the seller",
    Order.Status.PACKED: "Seller packed your item at the Bengaluru hub",
    Order.Status.SHIPPED: "Handed over to Ekart courier partner",
    Order.Status.OUT_FOR_DELIVERY: "Out for delivery in your area",
    Order.Status.DELIVERED: "Delivered - thanks for shopping with BazaarNoon",
    Order.Status.CANCELLED: "Order cancelled",
    Order.Status.RETURN_REQUESTED: "Return requested by customer",
    Order.Status.RETURNED: "Returned and refund processed",
}

# customer, status, days ago, payment, product names, coupon
ORDER_SEEDS = [
    ("demo", Order.Status.DELIVERED, 21, Order.PaymentMethod.UPI,
     ["Atomic Habits by James Clear (Paperback)", "Tata Tea Premium Leaf 1 kg"], "WELCOME200"),
    ("demo", Order.Status.PLACED, 0, Order.PaymentMethod.COD,
     ["boAt Rockerz 450 Bluetooth Headphone"], ""),
    ("demo", Order.Status.SHIPPED, 3, Order.PaymentMethod.CARD,
     ["Nike Revolution 7 Running Shoes", "Levi's Men 511 Slim Fit Jeans"], "BBD10"),
    ("demo", Order.Status.DELIVERED, 34, Order.PaymentMethod.UPI,
     ["HP Pavilion 15 (Intel i5 12th Gen, 16 GB)"], "TECH1500"),
    ("priya", Order.Status.DELIVERED, 9, Order.PaymentMethod.UPI,
     ["Mamaearth Vitamin C Face Serum 30 ml", "Lakmé Absolute Matte Lipstick"], ""),
    ("arjun", Order.Status.OUT_FOR_DELIVERY, 2, Order.PaymentMethod.COD,
     ["Redmi Note 13 Pro 5G (Midnight Black, 128 GB)"], ""),
    ("neha", Order.Status.RETURN_REQUESTED, 11, Order.PaymentMethod.CARD,
     ["Libas Women Printed A-Line Kurta"], "FASHION20"),
    ("rahul", Order.Status.CANCELLED, 6, Order.PaymentMethod.COD,
     ["Mi 108 cm (43 inch) 4K LED Smart TV"], ""),
    ("kavya", Order.Status.PACKED, 1, Order.PaymentMethod.UPI,
     ["Prestige Omega Deluxe Non-Stick Cookware Set", "Milton Thermosteel Flip Lid Flask 1 L"], ""),
    ("vikram", Order.Status.RETURNED, 18, Order.PaymentMethod.CARD,
     ["Adidas Ultraboost Light Running Shoes"], ""),
]


class Command(BaseCommand):
    help = "Seed a realistic India-first catalogue, demo shoppers and orders."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all store data before seeding (safe: demo data only).",
        )

    # -- entry point --------------------------------------------------------
    def handle(self, *args, **options):
        random.seed(2026)
        with transaction.atomic():
            if options["flush"]:
                self._flush()
            self._pincodes()
            self._people()
            categories = self._categories()
            brands = self._brands()
            products = self._products(categories, brands)
            self._reviews(products)
            self._wishlist(products)
            self._coupons()
            self._orders(products)
            self._demo_cart(products)

        self.stdout.write(self.style.SUCCESS("\nBazaarNoon is ready."))
        self.stdout.write("  Storefront  : http://127.0.0.1:8010/")
        self.stdout.write("  Admin       : admin / Admin@12345")
        self.stdout.write("  Manager     : manager / Manager@123")
        self.stdout.write("  Customer    : demo / Demo@12345")
        self.stdout.write(f"  Products    : {Product.objects.count()}")
        self.stdout.write(f"  Orders      : {Order.objects.count()}\n")

    # -- helpers -------------------------------------------------------------
    def _flush(self):
        for model in (
            ReturnRequest,
            OrderEvent,
            OrderItem,
            Order,
            CartItem,
            Cart,
            Review,
            WishlistItem,
            RecentlyViewed,
            ProductImage,
            Product,
            Brand,
            Category,
            Coupon,
            Pincode,
            Address,
            User,
        ):
            model.objects.all().delete()
        self.stdout.write("  Flushed existing demo data.")

    def _pincodes(self):
        for row in PINCODES:
            code, city, state, eta_min, eta_max, cod = row[:6]
            serviceable = row[6] if len(row) > 6 else True
            Pincode.objects.update_or_create(
                pincode=code,
                defaults={
                    "city": city,
                    "state": state,
                    "eta_min_days": eta_min,
                    "eta_max_days": eta_max,
                    "cod_available": cod,
                    "is_serviceable": serviceable,
                },
            )

    def _people(self):
        admin, _ = User.objects.get_or_create(username="admin")
        admin.email = "admin@bazaarnoon.in"
        admin.first_name = "Aarav"
        admin.last_name = "Kapoor"
        admin.role = Role.ADMIN
        admin.is_staff = True
        admin.is_superuser = True
        admin.phone = "9900000001"
        admin.set_password("Admin@12345")
        admin.save()

        manager, _ = User.objects.get_or_create(username="manager")
        manager.email = "manager@bazaarnoon.in"
        manager.first_name = "Meera"
        manager.last_name = "Nair"
        manager.role = Role.ADMIN
        manager.is_staff = True
        manager.phone = "9900000002"
        manager.set_password("Manager@123")
        manager.save()

        demo, _ = User.objects.get_or_create(username="demo")
        demo.email = "demo@bazaarnoon.in"
        demo.first_name = "Rohan"
        demo.last_name = "Gupta"
        demo.role = Role.CUSTOMER
        demo.phone = "9876543210"
        demo.set_password("Demo@12345")
        demo.save()
        for index, (label, line1, line2, city, state, pincode) in enumerate(ADDRESS_BOOK):
            Address.objects.get_or_create(
                user=demo,
                label=label,
                defaults={
                    "full_name": "Rohan Gupta",
                    "phone": "9876543210",
                    "line1": line1,
                    "line2": line2,
                    "city": city,
                    "state": state,
                    "pincode": pincode,
                    "is_default": index == 0,
                },
            )

        for username, first, last, email, phone in PEOPLE:
            user, _ = User.objects.get_or_create(username=username)
            user.first_name = first
            user.last_name = last
            user.email = email
            user.phone = phone
            user.role = Role.CUSTOMER
            user.set_password("Test@12345")
            user.save()
            if not user.addresses.exists():
                Address.objects.create(
                    user=user,
                    label="Home",
                    full_name=f"{first} {last}",
                    phone=phone,
                    line1=f"{random.randint(1, 90)}, {random.choice(['Green Park', 'Lake View', 'MG Road', 'Sector 21'])}",
                    city=random.choice(["Bengaluru", "Mumbai", "New Delhi", "Hyderabad", "Pune"]),
                    state="Karnataka",
                    pincode=random.choice(["560001", "400001", "110001", "500001", "411001"]),
                    is_default=True,
                )

    def _categories(self):
        result = {}
        for name, icon, position, description in CATEGORIES:
            category, _ = Category.objects.update_or_create(
                name=name,
                defaults={
                    "icon": icon,
                    "position": position,
                    "description": description,
                    "is_active": True,
                },
            )
            result[name] = category
        return result

    def _brands(self):
        result = {}
        for name, tagline in BRANDS:
            brand, _ = Brand.objects.update_or_create(
                name=name, defaults={"tagline": tagline, "is_active": True}
            )
            result[name] = brand
        return result

    def _products(self, categories, brands):
        products = []
        for index, row in enumerate(PRODUCTS):
            (name, brand, category, mrp, price, stock, image, rating, ratings,
             sold, badge, specs, description, delivery, warranty) = row
            product, _ = Product.objects.update_or_create(
                name=name,
                defaults={
                    "brand": brands[brand],
                    "category": categories[category],
                    "mrp": Decimal(mrp),
                    "price": Decimal(price),
                    "stock": stock,
                    "image_url": IMG.format(image),
                    "rating": Decimal(str(rating)),
                    "rating_count": ratings,
                    "review_count": ratios(ratings),
                    "sold_count": sold,
                    "badge": badge,
                    "highlights": specs,
                    "description": description,
                    "delivery_days": delivery,
                    "warranty": warranty,
                    "sku": f"BN-{category[:3].upper()}-{1000 + index}",
                    "is_active": True,
                    "is_featured": sold >= 3000,
                    "cod_available": price <= 50000,
                    "free_delivery": price >= 999,
                    "return_days": 7 if price >= 999 else 10,
                },
            )
            gallery = GALLERY.get(category, [image])
            urls = [product.image_url] + [IMG.format(g) for g in gallery if g != image][:2]
            for position, url in enumerate(urls):
                ProductImage.objects.get_or_create(
                    product=product, position=position, defaults={"url": url, "alt": name}
                )
            products.append(product)
        return products

    def _reviews(self, products):
        customers = list(User.objects.filter(role=Role.CUSTOMER))
        if not customers:
            return
        for index, product in enumerate(products):
            reviewers = customers[index % len(customers):] + customers[: index % len(customers)]
            count = 2 + (index % 4)
            for offset in range(count):
                user = reviewers[offset % len(reviewers)]
                rating, title, body = REVIEW_SNIPPETS[(index + offset) % len(REVIEW_SNIPPETS)]
                if offset == 0 and product.rating >= Decimal("4.4"):
                    rating = 5
                Review.objects.get_or_create(
                    product=product,
                    user=user,
                    defaults={"rating": rating, "title": title, "body": body, "is_verified_purchase": offset % 2 == 0},
                )

    def _wishlist(self, products):
        demo = User.objects.filter(username="demo").first()
        priya = User.objects.filter(username="priya").first()
        if not demo:
            return
        picks = [products[i] for i in (1, 9, 14, 29, 46) if i < len(products)]
        for product in picks:
            WishlistItem.objects.get_or_create(user=demo, product=product)
            if priya:
                WishlistItem.objects.get_or_create(user=priya, product=product)

    def _coupons(self):
        now = timezone.now()
        for index, (code, description, kind, value, minimum, cap, usage) in enumerate(COUPONS):
            Coupon.objects.update_or_create(
                code=code,
                defaults={
                    "description": description,
                    "discount_type": kind,
                    "value": Decimal(value),
                    "min_order_value": Decimal(minimum),
                    "max_discount": Decimal(cap) if cap else None,
                    "usage_limit": usage,
                    "per_user_limit": 2,
                    "valid_from": now - timedelta(days=10),
                    "valid_to": now + timedelta(days=75 - index * 5),
                    "is_active": True,
                },
            )

    def _orders(self, products):
        catalogue = {product.name: product for product in products}
        for index, (username, status, days_ago, payment, names, coupon_code) in enumerate(ORDER_SEEDS):
            user = User.objects.filter(username=username).first()
            if not user:
                continue
            if Order.objects.filter(invoice_number=f"INV/SEED-{index:02d}").exists():
                continue
            line_items = [(catalogue[name], 1 + (index + pos) % 2) for pos, name in enumerate(names) if name in catalogue]
            if not line_items:
                continue
            address = user.addresses.first()
            if address is None:
                continue
            self._build_order(user, address, line_items, status, days_ago, payment, coupon_code, index)

    def _build_order(self, user, address, line_items, status, days_ago, payment, coupon_code, index):
        coupon = Coupon.objects.filter(code=coupon_code).first() if coupon_code else None
        subtotal = sum((product.price * qty for product, qty in line_items), Decimal("0.00"))
        totals = quote(subtotal, coupon=coupon, payment_method=payment, products=[p for p, _ in line_items])
        billing = {field: totals[field] for field in BILLING_FIELDS}
        paid = payment != Order.PaymentMethod.COD
        if status in {Order.Status.CANCELLED, Order.Status.RETURNED}:
            payment_status = Order.PaymentStatus.REFUNDED if paid else Order.PaymentStatus.PENDING
        elif status == Order.Status.DELIVERED:
            payment_status = Order.PaymentStatus.PAID
        else:
            payment_status = Order.PaymentStatus.PAID if paid else Order.PaymentStatus.PENDING
        when = timezone.now() - timedelta(days=days_ago, hours=random.randint(0, 12))

        order = Order.objects.create(
            user=user,
            status=Order.Status.PLACED,
            payment_method=payment,
            payment_status=payment_status,
            payment_reference=f"PAY{when:%y%m%d%H%M}{user.pk:03d}" if paid else "",
            coupon=coupon,
            coupon_code=coupon.code if coupon else "",
            delivery_eta=(when + timedelta(days=4)).date(),
            shipping_name=address.full_name,
            shipping_phone=address.phone,
            shipping_line1=address.line1,
            shipping_line2=address.line2,
            shipping_city=address.city,
            shipping_state=address.state,
            shipping_pincode=address.pincode,
            invoice_number=f"INV/SEED-{index:02d}",
            **billing,
        )
        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    product=product,
                    product_name=product.name,
                    product_brand=product.brand.name if product.brand_id else "",
                    image_url=product.image_url,
                    unit_price=product.price,
                    unit_mrp=product.mrp,
                    quantity=qty,
                )
                for product, qty in line_items
            ]
        )

        timeline = self._timeline(status)
        for step_index, step in enumerate(timeline):
            OrderEvent.objects.create(
                order=order,
                status=step,
                note=EVENT_NOTES.get(step, ""),
                location=f"{address.city}, {address.pincode}" if step in PIPELINE[2:] else "Bengaluru hub",
            )
        Order.objects.filter(pk=order.pk).update(created_at=when, updated_at=when)
        OrderEvent.objects.filter(order=order).update(created_at=when)

        order.status = status
        if status == Order.Status.DELIVERED:
            order.delivered_at = when + timedelta(days=3)
            order.payment_status = Order.PaymentStatus.PAID
        elif status == Order.Status.CANCELLED:
            order.cancelled_at = when + timedelta(hours=6)
            order.cancel_reason = "Changed my mind"
        elif status == Order.Status.RETURNED:
            order.delivered_at = when + timedelta(days=3)
        elif status == Order.Status.RETURN_REQUESTED:
            order.delivered_at = when + timedelta(days=3)
        order.save()

        if status in {Order.Status.RETURN_REQUESTED, Order.Status.RETURNED}:
            resolved = status == Order.Status.RETURNED
            ReturnRequest.objects.create(
                order=order,
                user=user,
                reason=ReturnRequest.Reason.DAMAGED,
                comment="The outer packaging was torn and the item had a scratch.",
                status=ReturnRequest.Status.REFUNDED if resolved else ReturnRequest.Status.REQUESTED,
                refund_amount=order.total_amount,
                admin_note="Approved after pickup verification." if resolved else "",
                resolved_at=when + timedelta(days=6) if resolved else None,
            )

    def _timeline(self, status):
        if status == Order.Status.CANCELLED:
            return [Order.Status.PLACED, Order.Status.CANCELLED]
        if status == Order.Status.RETURN_REQUESTED:
            return PIPELINE + [Order.Status.RETURN_REQUESTED]
        if status == Order.Status.RETURNED:
            return PIPELINE + [Order.Status.RETURN_REQUESTED, Order.Status.RETURNED]
        if status in PIPELINE:
            return PIPELINE[: PIPELINE.index(status) + 1]
        return [Order.Status.PLACED]

    def _demo_cart(self, products):
        demo = User.objects.filter(username="demo").first()
        if not demo:
            return
        cart, _ = Cart.objects.get_or_create(user=demo)
        wanted = {
            "boAt Rockerz 450 Bluetooth Headphone": (1, False),
            "Mamaearth Vitamin C Face Serum 30 ml": (2, False),
            "Puma Smashic Unisex Sneakers": (1, True),
        }
        for product in products:
            if product.name in wanted:
                quantity, saved = wanted[product.name]
                CartItem.objects.update_or_create(
                    cart=cart,
                    product=product,
                    defaults={"quantity": quantity, "saved_for_later": saved},
                )
        cart.coupon = Coupon.objects.filter(code="BBD10").first()
        cart.save(update_fields=["coupon", "updated_at"])


def ratios(count):
    """Approximate the number of written reviews behind a rating count."""
    return max(0, int(count * 0.02))

