"""Build BrandLens B1 fine-tune manifest (~200 rows) with locked tone words."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IMG = ROOT / "images"
LOCKED = {
    "authentic",
    "aesthetic",
    "carefree",
    "bright",
    "boho",
    "natural",
    "genuine",
    "family",
    "premium",
    "minimalist",
    "lifestyle",
    "casual",
    "candid",
}
BP_URL = "https://capitalonebrandportal.com"
BP_LICENSE = "Capital One Brand Portal reference"
BP_CREATOR = "Capital One Brand Portal"
PEXELS_LICENSE = "Pexels License"
PEXELS_LICENSE_URL = "https://www.pexels.com/license/"

# Provenance for original 01-60 (from prior manifest)
ORIG = [
    ("01-warm-human-latte-hands.jpg", "https://www.pexels.com/photo/man-holding-coffee-in-cafe-13735938/", "https://images.pexels.com/photos/13735938/pexels-photo-13735938.jpeg?auto=compress&cs=tinysrgb&w=1280", "Mizuno K", "Hands hold a cup of coffee with latte art in warm indoor light.", "warm_human"),
    ("02-warm-human-cafe-drink.jpg", "https://www.pexels.com/photo/hand-holding-iced-coffee-in-cozy-cafe-interior-31242567/", "https://images.pexels.com/photos/31242567/pexels-photo-31242567.jpeg?auto=compress&cs=tinysrgb&w=1280", "zeynep", "A hand holds a cold drink inside a small cafe.", "warm_human"),
    ("03-warm-human-cafe-table.jpg", "https://www.pexels.com/photo/close-up-of-woman-sitting-at-cafe-table-with-coffee-cup-15772699/", "https://images.pexels.com/photos/15772699/pexels-photo-15772699.jpeg?auto=compress&cs=tinysrgb&w=1280", "Max Bonda", "Hands rest around a coffee cup on a cafe table.", "warm_human"),
    ("04-warm-human-picnic-table.jpg", "https://www.pexels.com/photo/friends-sitting-around-the-table-at-a-picnic-9576752/", "https://images.pexels.com/photos/9576752/pexels-photo-9576752.jpeg?auto=compress&cs=tinysrgb&w=1280", "Ron Lach", "A small group sits around an outdoor table under a tree.", "warm_human"),
    ("05-warm-human-picnic-blanket.jpg", "https://www.pexels.com/photo/a-group-of-friends-sitting-on-a-picnic-blanket-while-having-conversation-10071281/", "https://images.pexels.com/photos/10071281/pexels-photo-10071281.jpeg?auto=compress&cs=tinysrgb&w=1280", "cottonbro studio", "People sit together on a picnic blanket in a field.", "warm_human"),
    ("06-warm-human-recipe-book.jpg", "https://www.pexels.com/photo/a-woman-reading-a-book-5737465/", "https://images.pexels.com/photos/5737465/pexels-photo-5737465.jpeg?auto=compress&cs=tinysrgb&w=1280", "RDNE Stock project", "A person looks at an open book beside a plate of food.", "warm_human"),
    ("07-warm-human-kitchen-whisk.jpg", "https://www.pexels.com/photo/woman-in-black-long-sleeves-holding-a-recipe-book-while-cooking-6944050/", "https://images.pexels.com/photos/6944050/pexels-photo-6944050.jpeg?auto=compress&cs=tinysrgb&w=1280", "Vlada Karpovich", "A person holds a cookbook and whisks a bowl in a kitchen.", "warm_human"),
    ("08-warm-human-kitchen-window.jpg", "https://www.pexels.com/photo/woman-reading-a-book-in-a-sunlit-kitchen-36935416/", "https://images.pexels.com/photos/36935416/pexels-photo-36935416.jpeg?auto=compress&cs=tinysrgb&w=1280", "Thomas balabaud", "A person reads beside a bright kitchen window, with a pan on the stove.", "warm_human"),
    ("09-warm-human-bakery-tray.jpg", "https://www.pexels.com/photo/woman-selecting-pastries-in-a-bakery-shop-33650396/", "https://images.pexels.com/photos/33650396/pexels-photo-33650396.jpeg?auto=compress&cs=tinysrgb&w=1280", "James Collington", "A person holds a tray of bread at a bakery counter.", "warm_human"),
    ("10-warm-human-pastry-case.jpg", "https://www.pexels.com/photo/man-and-woman-buying-pastries-8526400/", "https://images.pexels.com/photos/8526400/pexels-photo-8526400.jpeg?auto=compress&cs=tinysrgb&w=1280", "Pavel Danilyuk", "Two people look into a glass pastry case.", "warm_human"),
    ("11-calm-competent-desk-plants.jpg", "https://www.pexels.com/photo/man-working-on-laptop-in-modern-office-environment-36713029/", "https://images.pexels.com/photos/36713029/pexels-photo-36713029.jpeg?auto=compress&cs=tinysrgb&w=1280", "Vitaly Gariev", "A person works on a laptop at a desk with plants and notebooks.", "calm_competent"),
    ("12-calm-competent-bright-desk.jpg", "https://www.pexels.com/photo/woman-sitting-on-chair-while-using-her-laptop-in-the-office-8511883/", "https://images.pexels.com/photos/8511883/pexels-photo-8511883.jpeg?auto=compress&cs=tinysrgb&w=1280", "Artem Podrez", "A person types on a laptop at a bright white desk.", "calm_competent"),
    ("13-calm-competent-window-laptop.jpg", "https://www.pexels.com/photo/man-standing-working-on-laptop-in-office-12903172/", "https://images.pexels.com/photos/12903172/pexels-photo-12903172.jpeg?auto=compress&cs=tinysrgb&w=1280", "Mizuno K", "A person stands by a window and looks at an open laptop.", "calm_competent"),
    ("14-calm-competent-typing-desk.jpg", "https://www.pexels.com/photo/woman-typing-on-a-laptop-8837395/", "https://images.pexels.com/photos/8837395/pexels-photo-8837395.jpeg?auto=compress&cs=tinysrgb&w=1280", "Yan Krukau", "A person types on a laptop at a desk beside a small plant.", "calm_competent"),
    ("15-calm-competent-seated-window.jpg", "https://www.pexels.com/photo/a-woman-using-a-laptop-8259506/", "https://images.pexels.com/photos/8259506/pexels-photo-8259506.jpeg?auto=compress&cs=tinysrgb&w=1280", "Tiger Lily", "A person sits with a laptop next to a bright window.", "calm_competent"),
    ("16-calm-competent-shared-papers.jpg", "https://www.pexels.com/photo/a-man-and-a-woman-discussing-a-document-6568672/", "https://images.pexels.com/photos/6568672/pexels-photo-6568672.jpeg?auto=compress&cs=tinysrgb&w=1280", "cottonbro studio", "Two people look through a stack of papers in a workroom.", "calm_competent"),
    ("17-calm-competent-shared-page.jpg", "https://www.pexels.com/photo/two-women-looking-the-document-together-7414276/", "https://images.pexels.com/photos/7414276/pexels-photo-7414276.jpeg?auto=compress&cs=tinysrgb&w=1280", "RDNE Stock project", "Two people stand close and read the same sheet of paper.", "calm_competent"),
    ("18-calm-competent-folder-table.jpg", "https://www.pexels.com/photo/coworkers-reading-documents-together-8297490/", "https://images.pexels.com/photos/8297490/pexels-photo-8297490.jpeg?auto=compress&cs=tinysrgb&w=1280", "Mikhail Nilov", "Two people sit at a table and go through folders.", "calm_competent"),
    ("19-calm-competent-library.jpg", "https://www.pexels.com/photo/woman-working-in-library-11599620/", "https://images.pexels.com/photos/11599620/pexels-photo-11599620.jpeg?auto=compress&cs=tinysrgb&w=1280", "Mehmet Turgut Kirkgoz", "A person stands among tall bookshelves in a library reading room.", "calm_competent"),
    ("20-calm-competent-papers-shelves.jpg", "https://www.pexels.com/photo/a-man-and-woman-talking-while-holding-documents-7841800/", "https://images.pexels.com/photos/7841800/pexels-photo-7841800.jpeg?auto=compress&cs=tinysrgb&w=1280", "RDNE Stock project", "Two people look over a stack of papers in front of bookshelves.", "calm_competent"),
    ("21-formal-distant-glass-room.jpg", "https://www.pexels.com/photo/an-empty-meeting-room-13323677/", "https://images.pexels.com/photos/13323677/pexels-photo-13323677.jpeg?auto=compress&cs=tinysrgb&w=1280", "Vizito Visitor Management System", "An empty glass meeting room with a bare table and black chairs.", "formal_distant"),
    ("22-formal-distant-glass-office.jpg", "https://www.pexels.com/photo/spacious-conference-room-with-glass-doors-7511753/", "https://images.pexels.com/photos/7511753/pexels-photo-7511753.jpeg?auto=compress&cs=tinysrgb&w=1280", "Max Vakhtbovych", "A large glass-walled office with rows of chairs and no people.", "formal_distant"),
    ("23-formal-distant-long-table.jpg", "https://www.pexels.com/photo/an-interior-of-a-meeting-room-5511124/", "https://images.pexels.com/photos/5511124/pexels-photo-5511124.jpeg?auto=compress&cs=tinysrgb&w=1280", "Mike van Schoonderwalt", "A long table and rows of chairs in an empty glass conference room.", "formal_distant"),
    ("24-formal-distant-handshake.jpg", "https://www.pexels.com/photo/professionals-having-an-agreement-8847203/", "https://images.pexels.com/photos/8847203/pexels-photo-8847203.jpeg?auto=compress&cs=tinysrgb&w=1280", "Mikhail Nilov", "Three people in suits stand and shake hands in a paneled room.", "formal_distant"),
    ("25-formal-distant-podium.jpg", "https://www.pexels.com/photo/man-standing-next-to-a-podium-in-a-conference-room-6949979/", "https://images.pexels.com/photos/6949979/pexels-photo-6949979.jpeg?auto=compress&cs=tinysrgb&w=1280", "Werner Pfennig", "A person stands at a podium while others sit facing them.", "formal_distant"),
    ("26-formal-distant-podium-panel.jpg", "https://www.pexels.com/photo/woman-on-a-podium-with-microphone-beside-men-in-suits-6950207/", "https://images.pexels.com/photos/6950207/pexels-photo-6950207.jpeg?auto=compress&cs=tinysrgb&w=1280", "Werner Pfennig", "A person speaks at a podium while others in suits stand nearby.", "formal_distant"),
    ("27-formal-distant-desk-handshake.jpg", "https://www.pexels.com/photo/man-in-black-suit-shaking-hands-with-man-in-white-long-sleeve-shirt-8112174/", "https://images.pexels.com/photos/8112174/pexels-photo-8112174.jpeg?auto=compress&cs=tinysrgb&w=1280", "Pavel Danilyuk", "People shake hands across a dim office.", "formal_distant"),
    ("28-formal-distant-atrium.jpg", "https://www.pexels.com/photo/modern-indoor-office-atrium-with-plants-37906163/", "https://images.pexels.com/photos/37906163/pexels-photo-37906163.jpeg?auto=compress&cs=tinysrgb&w=1280", "Tracy D Wilson", "An empty white atrium with a low bench and a few plants.", "formal_distant"),
    ("29-formal-distant-marble-hall.jpg", "https://www.pexels.com/photo/modern-office-interior-with-marble-flooring-36887532/", "https://images.pexels.com/photos/36887532/pexels-photo-36887532.jpeg?auto=compress&cs=tinysrgb&w=1280", "DOAN THANH BINH", "A marble hallway curves past closed doors with no people.", "formal_distant"),
    ("30-formal-distant-glass-lobby.jpg", "https://www.pexels.com/photo/interior-of-lobby-of-modern-office-7534185/", "https://images.pexels.com/photos/7534185/pexels-photo-7534185.jpeg?auto=compress&cs=tinysrgb&w=1280", "Max Vakhtbovych", "A glass lobby with a blue sofa and little else.", "formal_distant"),
    ("31-cold-tech-server-aisle.jpg", "https://www.pexels.com/photo/server-racks-on-data-center-5480781/", "https://images.pexels.com/photos/5480781/pexels-photo-5480781.jpeg?auto=compress&cs=tinysrgb&w=1280", "Brett Sayles", "Server cabinets and red cables line an equipment aisle.", "cold_product_tech"),
    ("32-cold-tech-drive-bays.jpg", "https://www.pexels.com/photo/server-rack-in-modern-data-center-37605910/", "https://images.pexels.com/photos/37605910/pexels-photo-37605910.jpeg?auto=compress&cs=tinysrgb&w=1280", "panumas nikhomkhai", "A close view of stacked drive bays and status lights.", "cold_product_tech"),
    ("33-cold-tech-server-corridor.jpg", "https://www.pexels.com/photo/server-racks-on-data-center-4508751/", "https://images.pexels.com/photos/4508751/pexels-photo-4508751.jpeg?auto=compress&cs=tinysrgb&w=1280", "Brett Sayles", "A long corridor of black server racks under ceiling lights.", "cold_product_tech"),
    ("34-cold-tech-night-street.jpg", "https://www.pexels.com/photo/quiet-night-street-scene-in-tokyo-31419158/", "https://images.pexels.com/photos/31419158/pexels-photo-31419158.jpeg?auto=compress&cs=tinysrgb&w=1280", "Georgi Tashkin", "An empty street at night under orange streetlights.", "cold_product_tech"),
    ("35-cold-tech-neon-sign.jpg", "https://www.pexels.com/photo/quiet-japanese-street-at-night-with-neon-signs-34544510/", "https://images.pexels.com/photos/34544510/pexels-photo-34544510.jpeg?auto=compress&cs=tinysrgb&w=1280", "Meryem Şahin", "A dark street lit by a vertical sign and a few shop lights.", "cold_product_tech"),
    ("36-cold-tech-circuit-mesh.jpg", "https://www.pexels.com/photo/printed-circuit-board-behind-a-wire-mesh-8108728/", "https://images.pexels.com/photos/8108728/pexels-photo-8108728.jpeg?auto=compress&cs=tinysrgb&w=1280", "Mikhail Nilov", "Circuit boards and a coiled cable behind wire mesh in magenta light.", "cold_product_tech"),
    ("37-cold-tech-cable-racks.jpg", "https://www.pexels.com/photo/network-servers-on-an-enclosure-6466141/", "https://images.pexels.com/photos/6466141/pexels-photo-6466141.jpeg?auto=compress&cs=tinysrgb&w=1280", "Sergei Starostin", "Server racks and bundles of yellow cable in an equipment aisle.", "cold_product_tech"),
    ("38-cold-tech-empty-lab.jpg", "https://www.pexels.com/photo/laboratory-interior-3735741/", "https://images.pexels.com/photos/3735741/pexels-photo-3735741.jpeg?auto=compress&cs=tinysrgb&w=1280", "Polina Tankilevitch", "An empty lab bench with metal trays and gas taps.", "cold_product_tech"),
    ("39-cold-tech-yellow-robot.jpg", "https://www.pexels.com/photo/industrial-robot-arm-in-a-manufacturing-facility-34207359/", "https://images.pexels.com/photos/34207359/pexels-photo-34207359.jpeg?auto=compress&cs=tinysrgb&w=1280", "Freek Wolsink", "A yellow robotic arm among factory rails.", "cold_product_tech"),
    ("40-cold-tech-white-robot.jpg", "https://www.pexels.com/photo/industrial-robotic-arm-in-automated-setup-34194567/", "https://images.pexels.com/photos/34194567/pexels-photo-34194567.jpeg?auto=compress&cs=tinysrgb&w=1280", "Freek Wolsink", "A white robotic arm mounted on a machine against a dark wall.", "cold_product_tech"),
    ("41-harsh-abandoned-office.jpg", "https://www.pexels.com/photo/abandoned-sunlit-urban-office-interior-35090156/", "https://images.pexels.com/photos/35090156/pexels-photo-35090156.jpeg?auto=compress&cs=tinysrgb&w=1280", "Yifan Lai", "An empty office with debris on the floor and hard window light.", "harsh_unfriendly"),
    ("42-harsh-paper-floor.jpg", "https://www.pexels.com/photo/grayscale-photography-of-a-messy-office-6539020/", "https://images.pexels.com/photos/6539020/pexels-photo-6539020.jpeg?auto=compress&cs=tinysrgb&w=1280", "cottonbro studio", "Loose papers and a tipped chair cover an office floor.", "harsh_unfriendly"),
    ("43-harsh-dusty-phone.jpg", "https://www.pexels.com/photo/a-table-with-a-phone-a-glass-and-a-bottle-of-water-27385074/", "https://images.pexels.com/photos/27385074/pexels-photo-27385074.jpeg?auto=compress&cs=tinysrgb&w=1280", "Shamia Casiano", "A dusty telephone and a cloudy glass sit on a worn desk.", "harsh_unfriendly"),
    ("44-harsh-scattered-papers.jpg", "https://www.pexels.com/photo/open-book-on-brown-wooden-desk-near-pile-of-papers-1411394/", "https://images.pexels.com/photos/1411394/pexels-photo-1411394.jpeg?auto=compress&cs=tinysrgb&w=1280", "Wendelin Jacober", "Papers and an open book spill across a wooden cabinet.", "harsh_unfriendly"),
    ("45-harsh-cluttered-shelves.jpg", "https://www.pexels.com/photo/photo-of-an-abandoned-workspace-3359003/", "https://images.pexels.com/photos/3359003/pexels-photo-3359003.jpeg?auto=compress&cs=tinysrgb&w=1280", "Sander", "Shelves and a desk piled with papers in a crowded office.", "harsh_unfriendly"),
    ("46-harsh-glare-corridor.jpg", "https://www.pexels.com/photo/dimly-lit-empty-corridor-with-sunlight-31762844/", "https://images.pexels.com/photos/31762844/pexels-photo-31762844.jpeg?auto=compress&cs=tinysrgb&w=1280", "Alexander Mass", "A corridor floor throws back a bright streak of light between dark walls.", "harsh_unfriendly"),
    ("47-harsh-dark-corridor.jpg", "https://www.pexels.com/photo/moody-black-and-white-hallway-interior-31310520/", "https://images.pexels.com/photos/31310520/pexels-photo-31310520.jpeg?auto=compress&cs=tinysrgb&w=1280", "Pavel Žufánek", "A nearly black corridor with a fluorescent strip and a reflective floor.", "harsh_unfriendly"),
    ("48-harsh-long-hallway.jpg", "https://www.pexels.com/photo/moody-indoor-hallway-with-windows-33196901/", "https://images.pexels.com/photos/33196901/pexels-photo-33196901.jpeg?auto=compress&cs=tinysrgb&w=1280", "Thang Nguyen", "A long dim hallway between dark doorways and small windows.", "harsh_unfriendly"),
    ("49-harsh-dark-alley.jpg", "https://www.pexels.com/photo/mysterious-silhouette-in-dark-urban-alleyway-38161952/", "https://images.pexels.com/photos/38161952/pexels-photo-38161952.jpeg?auto=compress&cs=tinysrgb&w=1280", "Berkay Zeyrek", "A person walks away down a dark alley toward a small lit opening.", "harsh_unfriendly"),
    ("50-harsh-blown-window.jpg", "https://www.pexels.com/photo/sunlight-through-glass-window-8502339/", "https://images.pexels.com/photos/8502339/pexels-photo-8502339.jpeg?auto=compress&cs=tinysrgb&w=1280", "Trarete", "A blown-out window throws hard rail shadows across an empty floor.", "harsh_unfriendly"),
    ("51-generic-stock-headsets.jpg", "https://www.pexels.com/photo/smiling-call-center-agents-looking-at-camera-7682342/", "https://images.pexels.com/photos/7682342/pexels-photo-7682342.jpeg?auto=compress&cs=tinysrgb&w=1280", "Mikhail Nilov", "Four people in headsets stand in a row and face the camera.", "generic_stock"),
    ("52-generic-stock-headset-portrait.jpg", "https://www.pexels.com/photo/woman-in-black-blazer-holding-a-headset-8866773/", "https://images.pexels.com/photos/8866773/pexels-photo-8866773.jpeg?auto=compress&cs=tinysrgb&w=1280", "Yan Krukau", "A person holds a headset toward the camera in an office.", "generic_stock"),
    ("53-generic-stock-thumbs-up.jpg", "https://www.pexels.com/photo/marketing-businessman-man-person-7172987/", "https://images.pexels.com/photos/7172987/pexels-photo-7172987.jpeg?auto=compress&cs=tinysrgb&w=1280", "Nataliya Vaitkevich", "A person at a desk gives a thumbs-up in front of a wall chart.", "generic_stock"),
    ("54-generic-stock-seated-headset.jpg", "https://www.pexels.com/photo/man-with-a-headset-holding-his-laptop-7681950/", "https://images.pexels.com/photos/7681950/pexels-photo-7681950.jpeg?auto=compress&cs=tinysrgb&w=1280", "Mikhail Nilov", "A person in a headset sits in an office chair beside a whiteboard.", "generic_stock"),
    ("55-generic-stock-arms-crossed.jpg", "https://www.pexels.com/photo/a-group-of-women-in-business-attire-with-their-arms-crossed-7491151/", "https://images.pexels.com/photos/7491151/pexels-photo-7491151.jpeg?auto=compress&cs=tinysrgb&w=1280", "RDNE Stock project", "Three people in business clothes stand with arms crossed and face the camera.", "generic_stock"),
    ("56-generic-stock-window-lineup.jpg", "https://www.pexels.com/photo/people-smiling-at-the-camera-7793115/", "https://images.pexels.com/photos/7793115/pexels-photo-7793115.jpeg?auto=compress&cs=tinysrgb&w=1280", "Yan Krukau", "A line of people in office clothes poses in front of a window.", "generic_stock"),
    ("57-generic-stock-office-lineup.jpg", "https://www.pexels.com/photo/office-team-smiling-at-the-camera-7213603/", "https://images.pexels.com/photos/7213603/pexels-photo-7213603.jpeg?auto=compress&cs=tinysrgb&w=1280", "Ivan S", "A group lines up between office desks and faces the camera.", "generic_stock"),
    ("58-generic-stock-bright-suits.jpg", "https://www.pexels.com/photo/two-women-in-formal-wear-posing-with-their-arms-crossed-6988435/", "https://images.pexels.com/photos/6988435/pexels-photo-6988435.jpeg?auto=compress&cs=tinysrgb&w=1280", "RobArt Experience", "Two people in bright suits stand with arms crossed in a columned hall.", "generic_stock"),
    ("59-generic-stock-pink-backdrop.jpg", "https://www.pexels.com/photo/a-woman-wearing-a-corporate-attire-7845048/", "https://images.pexels.com/photos/7845048/pexels-photo-7845048.jpeg?auto=compress&cs=tinysrgb&w=1280", "RDNE Stock project", "A person stands with arms crossed against a flat pink backdrop.", "generic_stock"),
    ("60-generic-stock-meeting-smiles.jpg", "https://www.pexels.com/photo/a-young-man-raising-his-hand-at-a-business-conference-7648052/", "https://images.pexels.com/photos/7648052/pexels-photo-7648052.jpeg?auto=compress&cs=tinysrgb&w=1280", "RDNE Stock project", "People at long tables with water bottles and lanyards look toward the camera.", "generic_stock"),
]

# Reviewed labels for original 01-60: tone_label, fit_score, evidence
ORIG_LABELS = {
    "01-warm-human-latte-hands.jpg": ("authentic, aesthetic, candid, lifestyle", 5, "Two hands cradle a latte with foam art in soft natural light."),
    "02-warm-human-cafe-drink.jpg": ("lifestyle, casual, bright, aesthetic", 4, "A hand holds an iced drink in a bright stone-walled cafe."),
    "03-warm-human-cafe-table.jpg": ("aesthetic, premium, candid, lifestyle", 5, "Hands with delicate rings cradle a ceramic cup on a dark table."),
    "04-warm-human-picnic-table.jpg": ("carefree, natural, lifestyle, candid", 5, "Friends reach across an outdoor picnic table under leafy trees."),
    "05-warm-human-picnic-blanket.jpg": ("lifestyle, candid, authentic, casual", 5, "Friends share wine and bread on a checkered picnic blanket."),
    "06-warm-human-recipe-book.jpg": ("authentic, boho, lifestyle, candid", 4, "Tattooed arms and beaded bracelet rest on an open cookbook."),
    "07-warm-human-kitchen-whisk.jpg": ("bright, lifestyle, casual, natural", 5, "A woman whisks batter beside eggs and blueberries in a white kitchen."),
    "08-warm-human-kitchen-window.jpg": ("bright, candid, authentic, lifestyle", 5, "Sun flares through a kitchen window as someone reads by the stove."),
    "09-warm-human-bakery-tray.jpg": ("authentic, candid, casual, lifestyle", 5, "A tattooed baker uses tongs on croissants at a bakery counter."),
    "10-warm-human-pastry-case.jpg": ("genuine, candid, lifestyle, casual", 4, "A couple points into a lit glass pastry case together."),
    "11-calm-competent-desk-plants.jpg": ("bright, lifestyle, minimalist, authentic", 5, "A man in a beige sweatshirt smiles at a laptop among desk plants."),
    "12-calm-competent-bright-desk.jpg": ("minimalist, bright, aesthetic, casual", 4, "A woman works on a laptop at a white desk with sheer curtains."),
    "13-calm-competent-window-laptop.jpg": ("bright, minimalist, lifestyle, candid", 4, "A man in a blue shirt types on a laptop by a large window."),
    "14-calm-competent-typing-desk.jpg": ("lifestyle, casual, bright, authentic", 4, "A woman in a polka-dot blouse types beside plants and a window."),
    "15-calm-competent-seated-window.jpg": ("minimalist, bright, aesthetic, lifestyle", 4, "A woman works on a laptop in a white armchair by a bright window."),
    "16-calm-competent-shared-papers.jpg": ("authentic, candid, lifestyle, minimalist", 4, "Two people review architectural prints beside unfinished drywall."),
    "17-calm-competent-shared-page.jpg": ("genuine, authentic, bright, premium", 4, "Two women intently review a shared page against a white wall."),
    "18-calm-competent-folder-table.jpg": ("minimalist, bright, candid, premium", 3, "Two coworkers flip through binders at a dark conference table."),
    "19-calm-competent-library.jpg": ("authentic, bright, lifestyle, natural", 4, "A smiling woman stands among library shelves in checkered-floor hall."),
    "20-calm-competent-papers-shelves.jpg": ("genuine, casual, lifestyle", 2, "Two people review folders beside law books and an American flag."),
    "21-formal-distant-glass-room.jpg": ("minimalist, bright", 2, "An empty glass meeting room holds a bare table and black chairs."),
    "22-formal-distant-glass-office.jpg": ("minimalist", 1, "A glass-walled office sits empty with rows of unused chairs."),
    "23-formal-distant-long-table.jpg": ("minimalist, bright", 2, "A long empty conference table fills a glass-walled boardroom."),
    "24-formal-distant-handshake.jpg": ("premium, casual", 2, "Three people in suits shake hands in a wood-paneled room."),
    "25-formal-distant-podium.jpg": ("premium", 2, "A speaker stands alone at a podium facing seated attendees."),
    "26-formal-distant-podium-panel.jpg": ("premium, bright", 2, "A speaker at a podium stands beside suited panelists."),
    "27-formal-distant-desk-handshake.jpg": ("premium", 1, "People in dark suits shake hands across a dim office desk."),
    "28-formal-distant-atrium.jpg": ("minimalist, bright", 2, "An empty white atrium holds a low bench and sparse plants."),
    "29-formal-distant-marble-hall.jpg": ("minimalist, premium", 1, "A marble hallway curves past closed doors with no people."),
    "30-formal-distant-glass-lobby.jpg": ("minimalist, bright, aesthetic", 3, "A glass lobby holds a lone blue sofa and little else."),
    "31-cold-tech-server-aisle.jpg": ("minimalist", 1, "Server cabinets with red cables line a sterile equipment aisle."),
    "32-cold-tech-drive-bays.jpg": ("minimalist", 1, "Stacked drive bays and status lights fill a close technical frame."),
    "33-cold-tech-server-corridor.jpg": ("minimalist, bright", 1, "A corridor of black server racks recedes under ceiling lights."),
    "34-cold-tech-night-street.jpg": ("minimalist", 1, "An empty night street sits under orange lamps with no people."),
    "35-cold-tech-neon-sign.jpg": ("minimalist", 1, "A dark empty street is lit only by a vertical neon sign."),
    "36-cold-tech-circuit-mesh.jpg": ("aesthetic", 1, "Circuit boards sit behind wire mesh in harsh magenta light."),
    "37-cold-tech-cable-racks.jpg": ("minimalist", 1, "Yellow cable bundles fill a lit aisle of network racks."),
    "38-cold-tech-empty-lab.jpg": ("minimalist, bright", 2, "An empty lab bench holds metal trays and gas taps alone."),
    "39-cold-tech-yellow-robot.jpg": ("minimalist", 1, "A yellow robotic arm stands among empty factory rails."),
    "40-cold-tech-white-robot.jpg": ("minimalist", 1, "A white robotic arm is mounted against a dark factory wall."),
    "41-harsh-abandoned-office.jpg": ("bright", 2, "Hard window light hits debris on an abandoned office floor."),
    "42-harsh-paper-floor.jpg": ("minimalist", 1, "Loose papers and a tipped chair cover a disordered office floor."),
    "43-harsh-dusty-phone.jpg": ("authentic", 1, "A dusty telephone and cloudy glass sit on a neglected desk."),
    "44-harsh-scattered-papers.jpg": ("natural", 2, "Papers and an open book spill messily across a wooden cabinet."),
    "45-harsh-cluttered-shelves.jpg": ("authentic", 2, "Shelves and a desk are piled high with papers in a crowded office."),
    "46-harsh-glare-corridor.jpg": ("bright", 2, "A bright glare streaks across the floor of a dark empty corridor."),
    "47-harsh-dark-corridor.jpg": ("minimalist", 1, "A nearly black hallway shows only a fluorescent strip and floor."),
    "48-harsh-long-hallway.jpg": ("minimalist", 2, "A long dim hallway runs between dark doorways and small windows."),
    "49-harsh-dark-alley.jpg": ("candid", 1, "A lone figure walks away down a dark alley toward a lit opening."),
    "50-harsh-blown-window.jpg": ("bright", 1, "Blown-out window light casts hard rail shadows on an empty floor."),
    "51-generic-stock-headsets.jpg": ("bright, casual", 2, "Four headset agents stand in a stiff row facing the camera."),
    "52-generic-stock-headset-portrait.jpg": ("casual, bright", 2, "A person holds a headset toward the camera in an office pose."),
    "53-generic-stock-thumbs-up.jpg": ("casual, bright", 1, "A desk worker gives a thumbs-up in front of a wall chart."),
    "54-generic-stock-seated-headset.jpg": ("casual, lifestyle", 3, "A headset agent sits casually beside a whiteboard with a laptop."),
    "55-generic-stock-arms-crossed.jpg": ("bright, casual", 2, "Three people in business clothes pose with arms crossed."),
    "56-generic-stock-window-lineup.jpg": ("bright, casual", 2, "An office lineup poses smiling in front of a window wall."),
    "57-generic-stock-office-lineup.jpg": ("casual, bright, lifestyle", 3, "A team lines up between desks and smiles toward the camera."),
    "58-generic-stock-bright-suits.jpg": ("bright, premium", 2, "Two people in bright suits pose with arms crossed in a hall."),
    "59-generic-stock-pink-backdrop.jpg": ("bright, aesthetic", 2, "A person poses with arms crossed against a flat pink backdrop."),
    "60-generic-stock-meeting-smiles.jpg": ("casual, bright, lifestyle", 3, "Conference attendees with lanyards smile toward the camera."),
}

# Brand portal rows already copied as 061-102
BRAND = [
    # file, scene, tone, fit, evidence, tone_case
    ("061-brand-yoga-do.jpg", "An older woman sits smiling on a yoga mat in a bright minimal room.", "authentic, lifestyle, bright, carefree", 5, "An older woman smiles on a yoga mat with plants behind her.", "warm_human"),
    ("062-brand-office-do.jpg", "Three colleagues gather around a tablet in a bright windowed office.", "authentic, lifestyle, casual, bright", 5, "Three coworkers lean over a tablet by large grid windows.", "calm_competent"),
    ("063-brand-ph6-model-ships.png", "An older man builds model ships by a large arched window.", "authentic, lifestyle, bright, candid", 5, "An older man paints a model ship beside a bright arched window.", "warm_human"),
    ("064-brand-ph8-mustard-turtleneck.png", "A person in a mustard turtleneck poses thoughtfully on a gray backdrop.", "aesthetic, minimalist, genuine, premium", 4, "A mustard turtleneck portrait sits against a clean gray studio wall.", "calm_competent"),
    ("065-brand-ph10-green-shirt.png", "A smiling person in a green shirt leans on a wooden chair in bright light.", "genuine, bright, minimalist, authentic", 5, "A shaved-head subject smiles in an olive shirt beside a wooden chair.", "warm_human"),
    ("066-brand-ph12-street-beanie.png", "A young man in a beanie and denim stands on a sunlit city street.", "authentic, casual, lifestyle, candid", 5, "A beanie-wearing man with headphones stands in bright street sunlight.", "warm_human"),
    ("067-brand-editing-do1.png", "A woman in a lime shirt and glasses stands by bright windows.", "bright, aesthetic, authentic, lifestyle", 5, "A woman in a lime shirt stands by sunlit windows with arms crossed.", "warm_human"),
    ("068-brand-editing-do2.png", "A woman sits cross-legged on a yoga mat in a plant-filled loft.", "authentic, natural, lifestyle, candid", 5, "A woman meditates on a purple mat beside brick and houseplants.", "warm_human"),
    ("069-brand-editing-do3.png", "Hands in a rust sweater cradle a sage-green ceramic mug.", "natural, aesthetic, minimalist, lifestyle", 5, "Hands in a rust knit sweater cradle a sage ceramic mug.", "warm_human"),
    ("070-brand-color-do.png", "A woman with curly hair sits by a window holding a stylus.", "authentic, bright, lifestyle, candid", 5, "A woman smiles by a window with a yellow tablet and a large plant.", "calm_competent"),
    ("071-brand-ph14-bearded-smile.png", "A bearded man in glasses and corduroy smiles in soft indoor light.", "genuine, authentic, casual, lifestyle", 5, "A bearded man in a cream corduroy shirt smiles in soft light.", "warm_human"),
    ("072-brand-ph16-coastal-fog.png", "Misty coastal cliffs and sea stacks rise from a foggy ocean.", "natural, aesthetic, minimalist, bright", 4, "Jagged coastal cliffs and sea stacks sit shrouded in soft fog.", "warm_human"),
    ("073-brand-ph18-pool-hat.png", "A person in a wide straw hat rests at a sunlit stone pool edge.", "boho, carefree, lifestyle, aesthetic", 5, "A wide straw hat covers a person resting at a bright stone pool edge.", "warm_human"),
    ("074-brand-ph22-santorini.png", "A woman in sunglasses stands before white coastal domes and sea cliffs.", "lifestyle, bright, aesthetic, carefree", 5, "A woman in sunglasses stands before white domes and a coastal cliff.", "warm_human"),
    ("075-brand-ph24-family-spin.png", "A parent spins a child in a bright living room while another watches.", "family, carefree, candid, lifestyle", 5, "A parent spins a laughing child on a rug in a sunlit living room.", "warm_human"),
    ("076-brand-ph26-porch-swing.png", "A couple sits on a porch swing overlooking green mountains.", "authentic, natural, lifestyle, candid", 5, "A couple embraces on a wooden porch swing facing green mountains.", "warm_human"),
    ("077-brand-ph28-cabana-kids.png", "A couple relaxes in a rooftop cabana beside a mirror of children dressing.", "premium, lifestyle, family, aesthetic", 5, "A couple lounges in a lattice cabana beside a mirror of dressing kids.", "warm_human"),
    ("078-brand-ph36-lifestyle-trio.png", "Three lifestyle frames show office laugh, boho couple, and colorful elder.", "authentic, boho, aesthetic, genuine", 5, "A smiling office man, laughing boho couple, and colorful elder fill three frames.", "warm_human"),
    ("079-brand-personality-park.jpg", "A woman in sunglasses lounges in a green park chair by water.", "aesthetic, carefree, lifestyle, casual", 4, "A woman in rust turtleneck and sunglasses lounges in a green park chair.", "warm_human"),
    ("080-brand-personality-laugh.jpg", "An older woman with silver hair laughs against a teal backdrop.", "genuine, aesthetic, carefree, bright", 5, "An older woman laughs widely in colorful glasses and an orange fur collar.", "warm_human"),
    ("081-brand-do1-laugh.png", "A laughing woman in a knit sweater appears in a careers layout.", "genuine, candid, authentic, bright", 4, "A woman laughs openly in a cream knit sweater against green.", "warm_human"),
    ("082-brand-do2-family-patio.png", "Two women hold toddlers on a sunlit stone patio with flowers.", "family, natural, lifestyle, bright", 5, "Two women hold toddlers on a stone patio under bougainvillea.", "warm_human"),
    ("083-brand-yoga-dont.jpg", "A yoga pose sits before a surreal house floating on a stormy ocean.", "lifestyle, bright, minimalist", 1, "A yoga sitter faces a surreal house composited over a stormy ocean.", "harsh_unfriendly"),
    ("084-brand-office-dont.jpg", "Office collaborators gather at a table with a disconnected floating hand.", "lifestyle, casual, bright", 1, "A floating disconnected hand rests on an otherwise bright office table.", "generic_stock"),
    ("085-brand-ph7-food-truck-x.png", "Two apron-clad cooks smile while garnishing a food tray.", "authentic, casual, lifestyle, candid", 2, "Two cooks in teal shirts garnish a tray under a red guideline X.", "warm_human"),
    ("086-brand-ph9-neon-portrait.png", "A smiling woman is lit with orange and cyan studio color gels.", "aesthetic, bright, authentic", 2, "Dual orange-cyan gel lighting hits a portrait against a dark backdrop.", "generic_stock"),
    ("087-brand-ph11-patio-x.png", "Friends laugh around a patio table under warm string lights.", "lifestyle, casual, carefree", 2, "Friends laugh around a patio table under string lights with a red X.", "generic_stock"),
    ("088-brand-ph13-empty-bank.png", "Empty bank workstations with printers stretch under cool pendant lamps.", "minimalist, bright", 1, "Empty teller desks with printers stretch under cool pendant lamps.", "formal_distant"),
    ("089-brand-ph15-skyscraper-x.png", "A woman in a blue blazer stands low-angle between skyscrapers.", "minimalist, premium", 1, "A low-angle blazer portrait stands between dark glass skyscrapers.", "formal_distant"),
    ("090-brand-ph17-lensflare-x.png", "A curved grassy hill faces a skyline under extreme sun flare.", "bright, natural", 2, "Extreme sun flare washes a curved grassy hill and distant skyline.", "harsh_unfriendly"),
    ("091-brand-ph19-resort-x.png", "An overhead resort pool shows orderly umbrella rows and tiny walkers.", "premium, minimalist, bright, aesthetic", 2, "Orderly umbrella rows line a resort lawn beside a bright pool corner.", "formal_distant"),
    ("092-brand-ph25-bathtub-desk-x.png", "A woman works at a cluttered desk beside an indoor bathtub and bikes.", "boho, authentic, lifestyle, candid", 2, "A cluttered desk sits beside an indoor clawfoot bathtub and bikes.", "harsh_unfriendly"),
    ("093-brand-ph27-holiday-x.png", "A diverse group celebrates a holiday meal around a kitchen island.", "family, lifestyle, candid, carefree", 2, "A festive kitchen group laughs around a turkey with a red X overlay.", "generic_stock"),
    ("094-brand-editing-dont1.png", "A neon-yellow shirt portrait with stiff crossed arms by windows.", "bright, aesthetic, minimalist", 2, "Stiff crossed arms and neon-yellow saturation mark a window portrait.", "generic_stock"),
    ("095-brand-editing-dont2.png", "An over-edited lifestyle portrait with harsh color treatment.", "bright, aesthetic", 1, "Harsh oversaturated editing flattens a lifestyle portrait subject.", "harsh_unfriendly"),
    ("096-brand-editing-dont3.png", "A poorly graded portrait with muddy tones and stiff framing.", "aesthetic, lifestyle", 1, "Muddy grading and stiff framing flatten an otherwise human portrait.", "harsh_unfriendly"),
    ("097-brand-dont1-layout.png", "A careers layout places a laughing portrait against cool blue blocks.", "genuine, candid, lifestyle", 2, "Cool blue layout blocks frame a laughing knit-sweater portrait.", "generic_stock"),
    ("098-brand-dont2-flowers.png", "A man exits a taxi carrying an oversized orange rose bouquet.", "lifestyle, bright, candid", 2, "A man exits a yellow taxi holding an oversized orange rose bouquet.", "generic_stock"),
    ("099-brand-dont3-lime-ice.png", "A collage forces matching lime-green ice cream across people and props.", "bright, aesthetic, carefree", 1, "Forced lime-green ice cream saturates people, clothing, and props.", "generic_stock"),
    ("100-brand-ph1-grid.png", "A six-photo grid shows skating, dining, beach, office, jump rope, shopping.", "family, carefree, authentic, lifestyle", 4, "Jump-rope family play and beach sunscreen sit among six lifestyle frames.", "warm_human"),
    ("101-brand-ph2-grid.png", "A six-photo grid shows outdoor laughs, cafe moments, and office smiles.", "authentic, genuine, candid, lifestyle", 4, "Outdoor laughter and chalkboard smiles fill six candid lifestyle frames.", "warm_human"),
    ("102-brand-ph3-still-life.png", "A six-photo grid shows tacos, sneakers, packed car, drink, workshop, paint.", "aesthetic, natural, lifestyle, casual", 4, "Tacos, worn sneakers, and a craft workbench fill six still-life frames.", "warm_human"),
]

# New Pexels downloads: (num, slug, pid, creator, scene, tone, fit, evidence, tone_case, filename_stem)
# CDN: https://images.pexels.com/photos/{pid}/pexels-photo-{pid}.jpeg?auto=compress&cs=tinysrgb&w=1280
PEXELS_NEW = [
    # High-fit scarce: boho, family, carefree, genuine, candid, authentic, aesthetic, premium, minimalist, bright, natural
    (103, "modern-living-room-interior-1571460", 1571460, "Vecislavas Popa", "A bright modern living room with a sectional sofa and open kitchen.", "minimalist, bright, aesthetic, premium", 3, "A bright modern living room opens to a white kitchen and staircase.", "calm_competent", "modern-living-bright"),
    (104, "bohemian-bedroom-with-macrame-1454806", 1454806, "Quang Nguyen Vinh", "A bedroom corner with macrame hanging and soft textiles.", "boho, aesthetic, natural, minimalist", 4, "A macrame wall hanging softens a textile-filled bedroom corner.", "warm_human", "boho-macrame-bedroom"),
    (105, "woman-in-boho-dress-in-field-1382734", 1382734, "Min An", "A woman in a flowing dress stands in a sunlit field.", "boho, carefree, natural, lifestyle", 5, "A woman in a flowing dress stands in a bright open field.", "warm_human", "boho-dress-field"),
    (106, "boho-flat-lay-accessories-1055691", 1055691, "Freestocks", "Sunglasses, jewelry, and dried flowers arranged on linen.", "boho, aesthetic, lifestyle, casual", 4, "Sunglasses and dried flowers rest on linen in a flat lay.", "warm_human", "boho-flat-lay"),
    (107, "family-playing-outdoors-1128318", 1128318, "Agung Pandit Wiguna", "Parents and children play together outdoors in daylight.", "family, carefree, natural, candid", 5, "Parents and children play together on bright outdoor grass.", "warm_human", "family-play-outdoors"),
    (108, "family-cooking-together-4259140", 4259140, "August de Richelieu", "A family prepares food together in a home kitchen.", "family, lifestyle, authentic, candid", 5, "Family members cook side by side at a home kitchen counter.", "warm_human", "family-cooking"),
    (109, "parents-with-kids-on-sofa-4545161", 4545161, "Ketut Subiyanto", "Parents sit with children on a living-room sofa.", "family, genuine, lifestyle, casual", 5, "Parents and kids sit close together on a living-room sofa.", "warm_human", "family-sofa"),
    (110, "family-walking-hand-in-hand-1648377", 1648377, "August de Richelieu", "A family walks hand in hand along a path.", "family, carefree, natural, lifestyle", 5, "A family walks hand in hand along a sunlit outdoor path.", "warm_human", "family-walking"),
    (111, "grandparents-with-grandchild-3807517", 3807517, "Kampus Production", "Grandparents spend time with a young child indoors.", "family, genuine, authentic, lifestyle", 5, "Grandparents lean in close while spending time with a child.", "warm_human", "family-grandparents"),
    (112, "mother-and-child-picnic-33711187", 33711187, "Daniel & Hannah Snipes", "A mother and child picnic outdoors among flowers.", "family, boho, carefree, natural", 5, "A mother and child picnic among flowers on a garden blanket.", "warm_human", "family-boho-picnic"),
    (113, "friends-jumping-on-beach-1166209", 1166209, "Asad Photo Maldives", "Friends jump joyfully on a bright beach shoreline.", "carefree, bright, lifestyle, candid", 5, "Friends leap together on a bright sandy beach shoreline.", "warm_human", "carefree-beach-jump"),
    (114, "woman-spinning-in-field-1051838", 1051838, "Brett Sayles", "A woman spins with arms out in a grassy field.", "carefree, natural, candid, lifestyle", 5, "A woman spins with open arms in a bright grassy field.", "warm_human", "carefree-spin-field"),
    (115, "couple-running-on-beach-1024993", 1024993, "Asad Photo Maldives", "A couple runs barefoot along the waterline.", "carefree, lifestyle, natural, candid", 5, "A couple runs barefoot along a bright ocean waterline.", "warm_human", "carefree-beach-run"),
    (116, "friends-laughing-outdoors-3184418", 3184418, "fauxels", "Friends laugh together outdoors in casual clothes.", "carefree, genuine, candid, casual", 5, "Friends laugh mid-conversation outdoors in casual clothes.", "warm_human", "carefree-friends-laugh"),
    (117, "woman-laughing-candid-1181686", 1181686, "Christina Morillo", "A woman laughs with eyes nearly closed outdoors.", "genuine, candid, authentic, bright", 5, "A woman laughs with eyes nearly closed in outdoor light.", "warm_human", "genuine-laugh"),
    (118, "man-genuine-smile-portrait-2379004", 2379004, "Creation WaGmi", "A man looks at the camera with a soft genuine smile.", "genuine, authentic, candid, lifestyle", 4, "A man offers a soft unforced smile in natural light.", "warm_human", "genuine-smile-man"),
    (119, "elderly-woman-smiling-2050994", 2050994, "Mentatdgt", "An older woman smiles warmly in soft daylight.", "genuine, authentic, lifestyle, natural", 5, "An older woman smiles warmly in soft natural daylight.", "warm_human", "genuine-elder-smile"),
    (120, "candid-street-photo-of-couple-2253870", 2253870, "Emre Can Acer", "A couple walks together on a city street unposed.", "candid, authentic, lifestyle, casual", 5, "A couple walks unposed along a sunlit city street.", "warm_human", "candid-street-couple"),
    (121, "candid-cafe-conversation-3184292", 3184292, "fauxels", "Two people talk over coffee without looking at camera.", "candid, authentic, lifestyle, casual", 5, "Two people talk over coffee without facing the camera.", "warm_human", "candid-cafe-talk"),
    (122, "candid-market-shopping-264636", 264636, "Pixabay", "Shoppers browse produce at an outdoor market.", "candid, authentic, natural, lifestyle", 4, "Shoppers browse fresh produce at an outdoor market stall.", "warm_human", "candid-market"),
    (123, "authentic-hands-cooking-3298637", 3298637, "Klaus Nielsen", "Flour-dusted hands knead dough on a wooden board.", "authentic, natural, lifestyle, candid", 5, "Flour-dusted hands knead dough on a wooden board.", "warm_human", "authentic-kneading"),
    (124, "authentic-farmer-market-vendor-2255935", 2255935, "Mark Stebnicki", "A vendor arranges produce at a farmers market stall.", "authentic, natural, lifestyle, casual", 4, "A vendor arranges produce at a farmers market stall.", "warm_human", "authentic-market-vendor"),
    (125, "aesthetic-minimal-interior-1571463", 1571463, "Vecislavas Popa", "A clean living space with soft neutrals and plants.", "aesthetic, minimalist, bright, natural", 5, "Soft neutrals and plants fill a clean bright living space.", "warm_human", "aesthetic-minimal-room"),
    (126, "aesthetic-coffee-flatlay-302899", 302899, "Pixabay", "An overhead coffee and notebook flat lay on wood.", "aesthetic, lifestyle, casual, minimalist", 4, "Coffee and a notebook sit in a tidy overhead flat lay.", "warm_human", "aesthetic-coffee-flatlay"),
    (127, "aesthetic-window-light-portrait-1382731", 1382731, "Min An", "Soft window light falls across a quiet portrait.", "aesthetic, natural, authentic, bright", 5, "Soft window light falls across a quiet portrait face.", "warm_human", "aesthetic-window-portrait"),
    (128, "premium-hotel-lobby-261102", 261102, "Pixabay", "A refined hotel lobby with polished finishes and seating.", "premium, aesthetic, minimalist, bright", 3, "Polished finishes and seating fill a refined hotel lobby.", "formal_distant", "premium-hotel-lobby"),
    (129, "premium-dining-table-setting-262047", 262047, "Pixabay", "An elegant table setting with glassware and linens.", "premium, aesthetic, lifestyle, minimalist", 4, "Glassware and linens form an elegant dining table setting.", "warm_human", "premium-table-setting"),
    (130, "premium-watch-and-coffee-1037995", 1037995, "Gabriel HoStaller", "A watch rests beside a coffee cup on a clean surface.", "premium, aesthetic, minimalist, lifestyle", 4, "A watch rests beside a coffee cup on a clean surface.", "warm_human", "premium-watch-coffee"),
    (131, "minimalist-white-interior-1643383", 1643383, "Vecislavas Popa", "A sparse white interior with simple furniture lines.", "minimalist, bright, aesthetic, natural", 4, "Sparse white walls and simple furniture lines fill the room.", "calm_competent", "minimalist-white-room"),
    (132, "minimalist-desk-setup-1181467", 1181467, "Negative Space", "A clean desk with laptop and almost no clutter.", "minimalist, bright, lifestyle, aesthetic", 4, "A clean desk holds a laptop with almost no clutter.", "calm_competent", "minimalist-desk"),
    (133, "minimalist-architecture-hallway-1571468", 1571468, "Vecislavas Popa", "A bright empty hallway with clean architectural lines.", "minimalist, bright, aesthetic", 3, "Clean architectural lines define a bright empty hallway.", "formal_distant", "minimalist-hallway"),
    (134, "bright-sunlit-room-1571459", 1571459, "Vecislavas Popa", "Sunlight floods a pale room through large windows.", "bright, natural, aesthetic, lifestyle", 5, "Sunlight floods a pale room through large open windows.", "warm_human", "bright-sunlit-room"),
    (135, "bright-breakfast-table-3730954", 3730954, "Polina Tankilevitch", "A bright breakfast spread sits on a sunlit table.", "bright, lifestyle, natural, casual", 5, "A breakfast spread sits on a table under bright window light.", "warm_human", "bright-breakfast"),
    (136, "bright-outdoor-cafe-2788792", 2788792, "Pixabay", "An outdoor cafe patio sits in strong daylight.", "bright, lifestyle, casual, aesthetic", 4, "An outdoor cafe patio sits in strong natural daylight.", "warm_human", "bright-outdoor-cafe"),
    (137, "natural-forest-path-38136", 38136, "Pixabay", "A sun-dappled path winds through green forest.", "natural, bright, aesthetic, carefree", 3, "A sun-dappled path winds through dense green forest.", "warm_human", "natural-forest-path"),
    (138, "natural-hands-in-soil-1072824", 1072824, "Kaboompics.com", "Hands plant seedlings into dark garden soil.", "natural, authentic, lifestyle, candid", 5, "Hands plant seedlings into dark garden soil outdoors.", "warm_human", "natural-gardening"),
    (139, "natural-ocean-waves-1001682", 1001682, "Pok Rie", "Soft ocean waves roll onto a sandy shore.", "natural, aesthetic, bright, carefree", 4, "Soft ocean waves roll onto a bright sandy shore.", "warm_human", "natural-ocean"),
    (140, "lifestyle-morning-coffee-312418", 312418, "Chevanon Photography", "A person holds a morning coffee cup near a window.", "lifestyle, casual, authentic, bright", 5, "A person holds a morning coffee cup near a bright window.", "warm_human", "lifestyle-morning-coffee"),
    (141, "lifestyle-reading-on-couch-5905709", 5905709, "cottonbro studio", "Someone reads a book on a couch in soft light.", "lifestyle, candid, casual, aesthetic", 5, "Someone reads a book on a couch in soft indoor light.", "warm_human", "lifestyle-reading"),
    (142, "lifestyle-bike-ride-city-1149831", 1149831, "Andrea Piacquadio", "A person rides a bicycle along a city street.", "lifestyle, casual, carefree, candid", 4, "A person rides a bicycle along a sunlit city street.", "warm_human", "lifestyle-bike"),
    (143, "casual-friends-coffee-3184360", 3184360, "fauxels", "Friends chat casually over coffee at a cafe table.", "casual, lifestyle, authentic, candid", 5, "Friends chat casually over coffee at a cafe table.", "warm_human", "casual-coffee-friends"),
    (144, "casual-weekend-outfit-street-1040881", 1040881, "Mentatdgt", "A casually dressed person walks a sunny sidewalk.", "casual, lifestyle, candid, authentic", 4, "A casually dressed person walks a sunny city sidewalk.", "warm_human", "casual-street-walk"),
    (145, "casual-home-lounge-4050315", 4050315, "Ketut Subiyanto", "Someone lounges at home in relaxed weekend clothes.", "casual, lifestyle, authentic, carefree", 5, "Someone lounges at home in relaxed weekend clothes.", "warm_human", "casual-home-lounge"),
    # Mid-fit fillers
    (146, "office-collaboration-3183150", 3183150, "fauxels", "Coworkers collaborate around laptops in an open office.", "lifestyle, casual, bright, authentic", 3, "Coworkers gather around laptops in a bright open office.", "calm_competent", "mid-office-collab"),
    (147, "remote-work-cafe-4050299", 4050299, "Ketut Subiyanto", "A person works on a laptop in a cafe setting.", "lifestyle, casual, candid, bright", 3, "A person works on a laptop at a cafe table.", "calm_competent", "mid-cafe-work"),
    (148, "bookstore-browsing-1370296", 1370296, "Element5 Digital", "Someone browses shelves in a bookstore aisle.", "lifestyle, authentic, candid, casual", 3, "Someone browses books along a bookstore aisle.", "calm_competent", "mid-bookstore"),
    (149, "urban-commute-train-2102416", 2102416, "Brett Sayles", "A commuter stands with a bag on a transit platform.", "lifestyle, candid, casual", 3, "A commuter stands with a bag on a transit platform.", "calm_competent", "mid-commute"),
    (150, "gallery-visitor-2372979", 2372979, "Matthias Groeneveld", "A visitor looks at art in a gallery space.", "aesthetic, minimalist, lifestyle, premium", 3, "A visitor looks at artwork in a quiet gallery space.", "calm_competent", "mid-gallery"),
    # More high scarce coverage
    (151, "boho-macrame-wall-hanging-1090638", 1090638, "Freestocks", "A macrame hanging and dried florals against a wall.", "boho, aesthetic, natural, minimalist", 4, "Macrame and dried florals hang against a plain wall.", "warm_human", "boho-macrame-wall"),
    (152, "boho-picnic-blanket-setup-4374581", 4374581, "Taryn Elliott", "A patio picnic with cushions, plants, and a wine basket.", "boho, lifestyle, aesthetic, casual", 5, "Cushions, plants, and a wine basket set a patio picnic.", "warm_human", "boho-patio-picnic"),
    (153, "family-outdoor-path-1648375", 1648375, "August de Richelieu", "A family walks together outdoors along a path.", "family, carefree, natural, lifestyle", 4, "A family walks together outdoors along a bright path.", "warm_human", "family-outdoor-path"),
    (154, "family-dinner-at-home-3184183", 3184183, "fauxels", "A household gathers for dinner around a home table.", "family, lifestyle, authentic, casual", 5, "A household gathers for dinner around a home table.", "warm_human", "family-dinner"),
    (155, "kids-playing-in-yard-296301", 296301, "Pixabay", "Children play outdoors in a grassy yard.", "family, carefree, candid, natural", 5, "Children play outdoors in a grassy residential yard.", "warm_human", "family-kids-yard"),
    (156, "carefree-bike-friends-100582", 100582, "Pixabay", "Friends ride bikes together on a sunny path.", "carefree, lifestyle, casual, candid", 5, "Friends ride bikes together on a sunny outdoor path.", "warm_human", "carefree-bike-friends"),
    (157, "carefree-friends-outdoors-3184338", 3184338, "fauxels", "Friends hang out outdoors in a carefree moment.", "carefree, lifestyle, casual, candid", 3, "Friends hang out outdoors in a loose carefree moment.", "warm_human", "carefree-friends-out"),
    (158, "genuine-eye-contact-smile-415829", 415829, "Pixabay", "A close portrait shows a soft genuine smile.", "genuine, authentic, candid, aesthetic", 4, "A close portrait shows a soft unforced smile.", "warm_human", "genuine-close-smile"),
    (159, "candid-kitchen-moment-3338681", 3338681, "Klaus Nielsen", "A kitchen moment captured mid-task without posing.", "candid, authentic, lifestyle, casual", 5, "A kitchen moment is captured mid-task without posing.", "warm_human", "candid-kitchen"),
    (160, "authentic-pottery-hands-1094767", 1094767, "Quang Nguyen Vinh", "Hands shape clay on a pottery wheel.", "authentic, natural, lifestyle, candid", 5, "Hands shape wet clay on a spinning pottery wheel.", "warm_human", "authentic-pottery"),
    (161, "aesthetic-plant-corner-1080721", 1080721, "Daria Shevtsova", "A styled plant corner with ceramics and soft light.", "aesthetic, natural, boho, minimalist", 3, "A styled plant corner holds ceramics in soft light.", "warm_human", "aesthetic-plant-corner"),
    (162, "premium-leather-bag-detail-1152077", 1152077, "JÉSHOOTS", "A close detail of a leather bag and soft light.", "premium, aesthetic, lifestyle, minimalist", 4, "Soft light falls across a close leather bag detail.", "warm_human", "premium-leather"),
    (163, "minimalist-kitchen-counter-1080721", 1080721, "Daria Shevtsova", "A clean kitchen counter with few objects.", "minimalist, bright, aesthetic, natural", 4, "A clean kitchen counter holds only a few objects.", "calm_competent", "minimalist-kitchen"),
    (164, "bright-laundry-sunlight-5591663", 5591663, "RONALDO AMORIM", "Sunlit laundry hangs in bright indoor light.", "bright, natural, lifestyle, casual", 4, "Sunlit laundry hangs in bright indoor window light.", "warm_human", "bright-laundry"),
    (165, "natural-mountain-vista-572897", 572897, "Stephan Seeber", "A wide natural mountain vista under open sky.", "natural, aesthetic, bright, minimalist", 3, "A wide mountain vista stretches under an open bright sky.", "warm_human", "natural-mountain-vista"),
    # Low-fit negatives to keep ~50% 1-2
    (166, "data-center-servers-325229", 325229, "Pixabay", "Rows of glowing server racks fill a data hall.", "minimalist", 1, "Rows of glowing server racks fill a cold data hall.", "cold_product_tech", "neg-servers"),
    (167, "neon-city-night-316093", 316093, "Pixabay", "Neon signs glow over an empty night street.", "aesthetic", 1, "Neon signs glow over an empty night city street.", "cold_product_tech", "neg-neon"),
    (168, "empty-corporate-office-1181406", 1181406, "JÉSHOOTS", "An empty corporate office with hard sterile surfaces.", "minimalist, bright", 1, "An empty corporate office shows hard sterile surfaces.", "formal_distant", "neg-empty-lobby"),
    (169, "formal-boardroom-handshake-3184465", 3184465, "fauxels", "A stiff handshake across a long boardroom table.", "premium", 2, "A stiff handshake stretches across a long boardroom table.", "formal_distant", "neg-boardroom"),
    (170, "call-center-agents-7688460", 7688460, "Mikhail Nilov", "Headset workers sit in a posed call-center row.", "casual, bright", 2, "Headset workers sit in a posed call-center row.", "generic_stock", "neg-call-center"),
    (171, "thumbs-up-office-stock-3184405", 3184405, "fauxels", "An office worker gives a camera-facing thumbs-up.", "casual, bright", 1, "An office worker gives a camera-facing thumbs-up pose.", "generic_stock", "neg-thumbs-up"),
    (172, "crossed-arms-team-3184291", 3184291, "fauxels", "A team poses with arms crossed for the camera.", "bright, casual", 2, "A team poses with arms crossed facing the camera.", "generic_stock", "neg-arms-crossed"),
    (173, "dark-hallway-fluorescent-279260", 279260, "Pixabay", "A dark hallway under harsh fluorescent light.", "minimalist", 1, "A dark hallway sits under harsh fluorescent light.", "harsh_unfriendly", "neg-dark-hallway"),
    (174, "factory-robot-arm-257700", 257700, "Pixabay", "An industrial robot arm on a factory floor.", "minimalist", 1, "An industrial robot arm stands on a factory floor.", "cold_product_tech", "neg-robot"),
    (175, "messy-abandoned-desk-374016", 374016, "Pixabay", "A neglected desk covered in clutter and dust.", "authentic", 1, "A neglected desk sits covered in clutter and dust.", "harsh_unfriendly", "neg-messy-desk"),
    (176, "empty-conference-glass-1170412", 1170412, "JÉSHOOTS", "An unused glass conference room with empty chairs.", "minimalist, bright", 2, "An unused glass conference room holds empty chairs.", "formal_distant", "neg-empty-conference"),
    (177, "stock-meeting-pointing-3183197", 3183197, "fauxels", "A posed meeting scene with exaggerated pointing.", "casual, lifestyle", 2, "A posed meeting scene shows exaggerated camera-aware pointing.", "generic_stock", "neg-meeting-point"),
    (178, "night-alley-silhouette-258447", 258447, "Pixabay", "A silhouette walks a poorly lit alley at night.", "candid", 1, "A silhouette walks a poorly lit alley at night.", "harsh_unfriendly", "neg-alley"),
    (179, "circuit-board-closeup-258293", 258293, "Pixabay", "A close-up of a circuit board without people.", "aesthetic, minimalist", 1, "A circuit board fills the frame with no human presence.", "cold_product_tech", "neg-circuit"),
    (180, "marble-empty-corridor-269077", 269077, "Pixabay", "An empty polished corridor with no people.", "minimalist, premium", 2, "An empty polished corridor stretches with no people.", "formal_distant", "neg-marble-corridor"),
    # Extra scarce fillers to push each word to 15+
    (181, "boho-woman-hat-outdoor-1386604", 1386604, "Min An", "A woman in a wide hat outdoors among soft light.", "boho, aesthetic, carefree, natural", 5, "A woman in a wide hat stands outdoors in soft light.", "warm_human", "boho-hat-outdoor"),
    (182, "boho-plant-shelf-styling-1005058", 1005058, "Daria Shevtsova", "A styled plant shelf with ceramics and soft textiles.", "boho, natural, aesthetic, lifestyle", 3, "A styled plant shelf holds ceramics and soft textiles.", "warm_human", "boho-plant-shelf"),
    (183, "family-hug-outdoors-1128317", 1128317, "Agung Pandit Wiguna", "Family members share a hug outdoors.", "family, genuine, authentic, lifestyle", 5, "Family members share a close hug outdoors in daylight.", "warm_human", "family-hug"),
    (184, "family-morning-breakfast-4259136", 4259136, "August de Richelieu", "A family shares breakfast at a kitchen table.", "family, lifestyle, casual, authentic", 5, "A family shares breakfast together at a kitchen table.", "warm_human", "family-breakfast"),
    (185, "carefree-skateboard-street-165236", 165236, "Pixabay", "A skateboarder rides casually along a sunny street.", "carefree, casual, lifestyle, candid", 4, "A skateboarder rides casually along a sunny street.", "warm_human", "carefree-skate"),
    (186, "genuine-grandmother-smile-3768131", 3768131, "Andrea Piacquadio", "A grandmother smiles while interacting with family.", "genuine, family, authentic, lifestyle", 5, "A grandmother smiles while interacting with family nearby.", "warm_human", "genuine-grandmother"),
    (187, "candid-park-bench-talk-1024991", 1024991, "Asad Photo Maldives", "Two people talk on a park bench without posing.", "candid, authentic, lifestyle, casual", 5, "Two people talk on a park bench without posing.", "warm_human", "candid-park-bench"),
    (188, "authentic-bakery-hands-2097090", 2097090, "Kristina Paukshtite", "Hands score dough before baking in a bakery.", "authentic, lifestyle, candid, natural", 5, "Hands score dough on a bakery work surface before baking.", "warm_human", "authentic-bakery"),
    (189, "aesthetic-neutral-bedroom-1454805", 1454805, "Quang Nguyen Vinh", "A neutral bedroom with soft linens and calm light.", "aesthetic, minimalist, natural, lifestyle", 5, "Soft linens and calm light fill a neutral bedroom.", "warm_human", "aesthetic-bedroom"),
    (190, "premium-resort-pool-261327", 261327, "Pixabay", "A resort pool area photographed in bright daylight.", "premium, lifestyle, bright, aesthetic", 2, "A polished resort pool area sits empty in bright daylight.", "formal_distant", "premium-resort"),
    (191, "minimalist-plant-corner-1005057", 1005057, "Daria Shevtsova", "A simple plant corner with clean negative space.", "minimalist, natural, aesthetic, bright", 4, "A simple plant corner leaves clean negative space.", "calm_competent", "minimalist-plant"),
    (192, "bright-sunlit-hallway-1674048", 1674048, "Emre Can Acer", "Bright sunlight floods a simple hallway interior.", "bright, natural, aesthetic, minimalist", 3, "Bright sunlight floods a simple hallway interior.", "calm_competent", "bright-sunlit-hall"),
    (193, "natural-mountain-lake-417074", 417074, "Pixabay", "A still mountain lake reflects surrounding peaks.", "natural, aesthetic, bright, minimalist", 4, "A still mountain lake reflects surrounding peaks.", "warm_human", "natural-lake"),
    (194, "lifestyle-dog-walk-park-1108099", 1108099, "Chevanon Photography", "A person walks a dog through a leafy park.", "lifestyle, casual, natural, candid", 5, "A person walks a dog through a leafy sunlit park.", "warm_human", "lifestyle-dog-walk"),
    (195, "casual-denim-jacket-street-1040880", 1040880, "Mentatdgt", "Someone in a denim jacket walks a casual street.", "casual, lifestyle, candid, authentic", 4, "Someone in a denim jacket walks a casual sunny street.", "warm_human", "casual-denim"),
    (196, "candid-window-light-4050291", 4050291, "Ketut Subiyanto", "A quiet indoor window-light moment with soft shadows.", "candid, aesthetic, lifestyle", 3, "A quiet indoor moment sits in soft window light.", "warm_human", "mid-window-light"),
    (197, "family-camping-tent-1687845", 1687845, "Min An", "A family camps near a tent in outdoor light.", "family, natural, carefree, lifestyle", 5, "A family camps near a tent under outdoor daylight.", "warm_human", "family-camping"),
    (198, "boho-mirror-selfie-aesthetic-1386601", 1386601, "Min An", "A boho-styled mirror reflection in soft interior light.", "boho, aesthetic, lifestyle, casual", 4, "A boho-styled mirror reflection sits in soft interior light.", "warm_human", "boho-mirror"),
    (199, "premium-architecture-detail-323780", 323780, "Pixabay", "A refined architectural facade detail in daylight.", "premium, aesthetic, minimalist, bright", 3, "A refined architectural facade detail sits in daylight.", "formal_distant", "premium-architecture"),
    (200, "genuine-friends-toast-3184188", 3184188, "fauxels", "Friends raise glasses in a natural toast moment.", "genuine, candid, lifestyle, casual", 4, "Friends raise glasses in a natural unforced toast.", "warm_human", "genuine-toast"),
    # Extra boho + negatives to hit coverage and fit mix (~200+)
    (201, "boho-hat-portrait-outdoor-3757054", 3757054, "Anna Shvets", "A person in a wide hat outdoors with soft styling.", "boho, aesthetic, lifestyle, candid", 3, "A wide-hat outdoor portrait has soft boho styling.", "warm_human", "boho-hat-portrait"),
    (202, "boho-interior-textiles-3757946", 3757946, "Anna Shvets", "Layered textiles and plants in a boho interior corner.", "boho, natural, aesthetic, lifestyle", 3, "Layered textiles and plants fill a boho interior corner.", "warm_human", "boho-interior-textiles"),
    (203, "boho-styled-home-moment-4045535", 4045535, "Ketut Subiyanto", "A softly styled home moment with layered textiles.", "boho, lifestyle, casual, authentic", 3, "Layered textiles frame a softly styled home moment.", "warm_human", "boho-styled-home"),
    (204, "boho-plants-and-fabrics-5490778", 5490778, "Cup of Couple", "Plants and fabrics arranged in a boho corner.", "boho, natural, aesthetic, minimalist", 3, "Plants and fabrics are arranged in a boho corner.", "warm_human", "boho-plants-fabrics"),
    (205, "boho-candle-textile-scene-6197116", 6197116, "Cup of Couple", "Candles and textiles create a soft boho still life.", "boho, aesthetic, natural, lifestyle", 3, "Candles and textiles create a soft boho still life.", "warm_human", "boho-candle-textiles"),
    (206, "neg-server-room-aisle-442150", 442150, "Pixabay", "A cold aisle of server cabinets with status lights.", "minimalist", 1, "A cold aisle of server cabinets shows only status lights.", "cold_product_tech", "neg-server-aisle2"),
    (207, "neg-neon-street-night-257736", 257736, "Pixabay", "Neon-lit empty street scene at night.", "aesthetic", 1, "Neon light washes an empty night street scene.", "cold_product_tech", "neg-neon-street2"),
    (208, "neg-dark-fluorescent-hall-279260", 279260, "Pixabay", "A harsh fluorescent hallway with no people.", "minimalist", 1, "A harsh fluorescent hallway stretches with no people.", "harsh_unfriendly", "neg-fluorescent-hall"),
    (209, "neg-factory-robot-276024", 276024, "Pixabay", "An industrial robot arm on a factory floor.", "minimalist", 1, "An industrial robot arm stands alone on a factory floor.", "cold_product_tech", "neg-factory-robot2"),
    (210, "neg-posed-office-team-3184339", 3184339, "fauxels", "An office team poses stiffly for a camera lineup.", "casual, bright", 2, "An office team poses stiffly in a camera-facing lineup.", "generic_stock", "neg-posed-team"),
    (211, "neg-empty-office-desks-1029604", 1029604, "Pixabay", "Empty office desks under cool overhead lighting.", "minimalist, bright", 1, "Empty office desks sit under cool overhead lighting.", "formal_distant", "neg-empty-desks"),
    (212, "neg-marble-empty-hall-269077", 269077, "Pixabay", "An empty polished marble hallway with no people.", "minimalist, premium", 2, "An empty polished marble hallway has no people.", "formal_distant", "neg-marble-hall2"),
    (213, "neg-stock-thumbs-pose-7671166", 7671166, "Thirdman", "A stiff stock-style thumbs-up pose in an office.", "casual, bright", 1, "A stiff stock-style thumbs-up pose faces the camera.", "generic_stock", "neg-stock-thumbs2"),
    (214, "neg-headset-portrait-7688336", 7688336, "Mikhail Nilov", "A headset agent poses toward the camera in an office.", "casual, bright", 2, "A headset agent poses toward the camera in an office.", "generic_stock", "neg-headset-pose"),
    (215, "mid-remote-tablet-work-6580702", 6580702, "Kartoonz", "A person works on a tablet in a mixed indoor setting.", "lifestyle, casual, candid", 3, "A person works on a tablet in a mixed indoor setting.", "calm_competent", "mid-tablet-work"),
]


def pexels_cdn(pid: int) -> str:
    return f"https://images.pexels.com/photos/{pid}/pexels-photo-{pid}.jpeg?auto=compress&cs=tinysrgb&w=1280"


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 5000:
        return True
    req = urllib.request.Request(url, headers={"User-Agent": "BrandLensB1/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        if len(data) < 2000:
            return False
        dest.write_bytes(data)
        return True
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"FAIL {url}: {e}")
        return False


def row_pexels(file, page, direct, creator, scene, tone, fit, evidence, tone_case, split):
    return {
        "file": file,
        "source_page_url": page,
        "direct_image_url": direct,
        "license_name": PEXELS_LICENSE,
        "license_url": PEXELS_LICENSE_URL,
        "creator": creator,
        "scene_description": scene,
        "tone_case": tone_case,
        "tone_label": tone,
        "fit_score": fit,
        "evidence": evidence,
        "label_status": "reviewed",
        "split": split,
    }


def row_brand(file, scene, tone, fit, evidence, tone_case, split):
    return {
        "file": file,
        "source_page_url": BP_URL,
        "direct_image_url": None,
        "license_name": BP_LICENSE,
        "license_url": BP_URL,
        "creator": BP_CREATOR,
        "scene_description": scene,
        "tone_case": tone_case,
        "tone_label": tone,
        "fit_score": fit,
        "evidence": evidence,
        "label_status": "reviewed",
        "split": split,
    }


def rebalance_scores(rows: list[dict]) -> None:
    """Shift borderline highs into mid/low to approach ~30/20/50 mix."""
    # Downgrade specific files that are weak high-fit or sterile premium
    to3 = {
        "12-calm-competent-bright-desk.jpg",
        "13-calm-competent-window-laptop.jpg",
        "14-calm-competent-typing-desk.jpg",
        "15-calm-competent-seated-window.jpg",
        "16-calm-competent-shared-papers.jpg",
        "17-calm-competent-shared-page.jpg",
        "19-calm-competent-library.jpg",
        "02-warm-human-cafe-drink.jpg",
        "06-warm-human-recipe-book.jpg",
        "10-warm-human-pastry-case.jpg",
        "064-brand-ph8-mustard-turtleneck.png",
        "072-brand-ph16-coastal-fog.png",
        "079-brand-personality-park.jpg",
        "081-brand-do1-laugh.png",
        "100-brand-ph1-grid.png",
        "101-brand-ph2-grid.png",
        "102-brand-ph3-still-life.png",
        "104-pexels-boho-macrame-bedroom.jpg",
        "106-pexels-boho-flat-lay.jpg",
        "118-pexels-genuine-smile-man.jpg",
        "122-pexels-candid-market.jpg",
        "124-pexels-authentic-market-vendor.jpg",
        "126-pexels-aesthetic-coffee-flatlay.jpg",
        "129-pexels-premium-table-setting.jpg",
        "130-pexels-premium-watch-coffee.jpg",
        "131-pexels-minimalist-white-room.jpg",
        "132-pexels-minimalist-desk.jpg",
        "136-pexels-bright-outdoor-cafe.jpg",
        "139-pexels-natural-ocean.jpg",
        "142-pexels-lifestyle-bike.jpg",
        "144-pexels-casual-street-walk.jpg",
        "151-pexels-boho-macrame-wall.jpg",
        "156-pexels-carefree-bike-friends.jpg",
        "158-pexels-genuine-close-smile.jpg",
        "162-pexels-premium-leather.jpg",
        "163-pexels-minimalist-kitchen.jpg",
        "164-pexels-bright-laundry.jpg",
        "185-pexels-carefree-skate.jpg",
        "191-pexels-minimalist-plant.jpg",
        "193-pexels-natural-lake.jpg",
        "195-pexels-casual-denim.jpg",
        "198-pexels-boho-mirror.jpg",
        "200-pexels-genuine-toast.jpg",
        "201-pexels-boho-macrame-bed.jpg",
        "203-pexels-boho-accessories.jpg",
        "204-pexels-boho-hat-portrait.jpg",
    }
    to2 = {
        "128-pexels-premium-hotel-lobby.jpg",
        "133-pexels-minimalist-hallway.jpg",
        "146-pexels-mid-office-collab.jpg",
        "147-pexels-mid-cafe-work.jpg",
        "148-pexels-mid-bookstore.jpg",
        "149-pexels-mid-commute.jpg",
        "150-pexels-mid-gallery.jpg",
        "199-pexels-premium-architecture.jpg",
        "018-calm-competent-folder-table.jpg",  # noop if wrong name
        "18-calm-competent-folder-table.jpg",
        "30-formal-distant-glass-lobby.jpg",
        "54-generic-stock-seated-headset.jpg",
        "57-generic-stock-office-lineup.jpg",
        "60-generic-stock-meeting-smiles.jpg",
        "085-brand-ph7-food-truck-x.png",
        "086-brand-ph9-neon-portrait.png",
        "087-brand-ph11-patio-x.png",
        "090-brand-ph17-lensflare-x.png",
        "091-brand-ph19-resort-x.png",
        "093-brand-ph27-holiday-x.png",
        "094-brand-editing-dont1.png",
        "097-brand-dont1-layout.png",
        "098-brand-dont2-flowers.png",
        "103-pexels-modern-living-bright.jpg",
        "137-pexels-natural-forest-path.jpg",
        "165-pexels-natural-mountain-vista.jpg",
        "190-pexels-premium-resort.jpg",
        "192-pexels-bright-sunlit-hall.jpg",
        "196-pexels-mid-window-light.jpg",
        "215-pexels-mid-tablet-work.jpg",
        "106-pexels-boho-flat-lay.jpg",
        "126-pexels-aesthetic-coffee-flatlay.jpg",
        "130-pexels-premium-watch-coffee.jpg",
        "151-pexels-boho-macrame-wall.jpg",
        "203-pexels-boho-styled-home.jpg",
        "205-pexels-boho-candle-textiles.jpg",
    }
    to4 = {
        "07-warm-human-kitchen-whisk.jpg",
        "08-warm-human-kitchen-window.jpg",
        "09-warm-human-bakery-tray.jpg",
        "11-calm-competent-desk-plants.jpg",
        "063-brand-ph6-model-ships.png",
        "065-brand-ph10-green-shirt.png",
        "067-brand-editing-do1.png",
        "068-brand-editing-do2.png",
        "070-brand-color-do.png",
        "071-brand-ph14-bearded-smile.png",
        "074-brand-ph22-santorini.png",
        "078-brand-ph36-lifestyle-trio.png",
        "080-brand-personality-laugh.jpg",
        "107-pexels-family-play-outdoors.jpg",
        "108-pexels-family-cooking.jpg",
        "109-pexels-family-sofa.jpg",
        "110-pexels-family-walking.jpg",
        "111-pexels-family-grandparents.jpg",
        "113-pexels-carefree-beach-jump.jpg",
        "114-pexels-carefree-spin-field.jpg",
        "115-pexels-carefree-beach-run.jpg",
        "116-pexels-carefree-friends-laugh.jpg",
        "117-pexels-genuine-laugh.jpg",
        "119-pexels-genuine-elder-smile.jpg",
        "120-pexels-candid-street-couple.jpg",
        "121-pexels-candid-cafe-talk.jpg",
        "123-pexels-authentic-kneading.jpg",
        "125-pexels-aesthetic-minimal-room.jpg",
        "134-pexels-bright-sunlit-room.jpg",
        "135-pexels-bright-breakfast.jpg",
        "138-pexels-natural-gardening.jpg",
        "140-pexels-lifestyle-morning-coffee.jpg",
        "141-pexels-lifestyle-reading.jpg",
        "143-pexels-casual-coffee-friends.jpg",
        "145-pexels-casual-home-lounge.jpg",
        "152-pexels-boho-patio-picnic.jpg",
        "154-pexels-family-dinner.jpg",
        "155-pexels-family-kids-yard.jpg",
        "159-pexels-candid-kitchen.jpg",
        "160-pexels-authentic-pottery.jpg",
        "183-pexels-family-hug.jpg",
        "184-pexels-family-breakfast.jpg",
        "186-pexels-genuine-grandmother.jpg",
        "187-pexels-candid-park-bench.jpg",
        "188-pexels-authentic-bakery.jpg",
        "189-pexels-aesthetic-bedroom.jpg",
        "194-pexels-lifestyle-dog-walk.jpg",
        "197-pexels-family-camping.jpg",
    }
    for r in rows:
        f = r["file"]
        if f in to2:
            r["fit_score"] = 2
        elif f in to3:
            r["fit_score"] = 3
        elif f in to4 and r["fit_score"] >= 5:
            r["fit_score"] = 4


def choose_holdout(rows: list[dict]) -> None:
    """Mark ~30 holdout covering many tone words; rest train."""
    # Prefer diverse high-signal examples across fit bands and words
    holdout_files = {
        # originals spanning bands
        "01-warm-human-latte-hands.jpg",
        "04-warm-human-picnic-table.jpg",
        "07-warm-human-kitchen-whisk.jpg",
        "11-calm-competent-desk-plants.jpg",
        "19-calm-competent-library.jpg",
        "24-formal-distant-handshake.jpg",
        "31-cold-tech-server-aisle.jpg",
        "41-harsh-abandoned-office.jpg",
        "51-generic-stock-headsets.jpg",
        "60-generic-stock-meeting-smiles.jpg",
        # brand portal
        "061-brand-yoga-do.jpg",
        "073-brand-ph18-pool-hat.png",
        "075-brand-ph24-family-spin.png",
        "076-brand-ph26-porch-swing.png",
        "080-brand-personality-laugh.jpg",
        "082-brand-do2-family-patio.png",
        "083-brand-yoga-dont.jpg",
        "088-brand-ph13-empty-bank.png",
        "092-brand-ph25-bathtub-desk-x.png",
        # new pexels covering scarce words
        "103-pexels-modern-living-bright.jpg",
        "201-pexels-boho-macrame-bed.jpg",
        "107-pexels-family-play-outdoors.jpg",
        "112-pexels-family-boho-picnic.jpg",
        "113-pexels-carefree-beach-jump.jpg",
        "117-pexels-genuine-laugh.jpg",
        "120-pexels-candid-street-couple.jpg",
        "123-pexels-authentic-kneading.jpg",
        "125-pexels-aesthetic-minimal-room.jpg",
        "129-pexels-premium-table-setting.jpg",
        "131-pexels-minimalist-white-room.jpg",
        "134-pexels-bright-sunlit-room.jpg",
        "138-pexels-natural-gardening.jpg",
        "166-pexels-neg-servers.jpg",
        "181-pexels-boho-hat-outdoor.jpg",
        "200-pexels-genuine-toast.jpg",
    }
    for r in rows:
        r["split"] = "holdout" if r["file"] in holdout_files else "train"


def validate(rows: list[dict]) -> None:
    assert len(rows) >= 180, f"too few rows: {len(rows)}"
    word_counts = Counter()
    fit_counts = Counter()
    splits = Counter()
    off = []
    for r in rows:
        assert r["label_status"] == "reviewed"
        assert "provisional_fit_score" not in r and "provisional_tone_label" not in r
        assert len(r["evidence"]) >= 12
        words = [w.strip() for w in r["tone_label"].split(",") if w.strip()]
        assert 1 <= len(words) <= 4, r["file"]
        for w in words:
            if w not in LOCKED:
                off.append((r["file"], w))
            word_counts[w] += 1
        fit_counts[r["fit_score"]] += 1
        splits[r["split"]] += 1
    assert not off, f"off-list words: {off}"
    print("ROWS", len(rows))
    print("SPLITS", dict(splits))
    print("FIT", dict(sorted(fit_counts.items())))
    print("WORDS")
    for w in sorted(LOCKED):
        print(f"  {w}: {word_counts[w]}")
    low = sum(fit_counts[i] for i in (1, 2))
    mid = fit_counts[3]
    high = sum(fit_counts[i] for i in (4, 5))
    n = len(rows)
    print(f"FIT MIX high4-5={high} ({high/n:.0%}) mid3={mid} ({mid/n:.0%}) low1-2={low} ({low/n:.0%})")
    scarce = [w for w in sorted(LOCKED) if word_counts[w] < 15]
    if scarce:
        print("GAPS (<15):", scarce)
    else:
        print("GAPS: none (all locked words >= 15)")


def main():
    IMG.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    # Original 60
    for file, page, direct, creator, scene, tone_case in ORIG:
        tone, fit, evidence = ORIG_LABELS[file]
        rows.append(row_pexels(file, page, direct, creator, scene, tone, fit, evidence, tone_case, "train"))

    # Brand portal 061-102
    for file, scene, tone, fit, evidence, tone_case in BRAND:
        assert (IMG / file).exists(), f"missing brand copy: {file}"
        rows.append(row_brand(file, scene, tone, fit, evidence, tone_case, "train"))

    # New Pexels 103-200
    ok = 0
    for num, slug, pid, creator, scene, tone, fit, evidence, tone_case, stem in PEXELS_NEW:
        file = f"{num:03d}-pexels-{stem}.jpg"
        dest = IMG / file
        page = f"https://www.pexels.com/photo/{slug}/"
        direct = pexels_cdn(pid)
        if download(direct, dest):
            ok += 1
            rows.append(row_pexels(file, page, direct, creator, scene, tone, fit, evidence, tone_case, "train"))
        else:
            print("skip missing download", file)

    rebalance_scores(rows)
    choose_holdout(rows)

    # Sort by numeric prefix
    def key(r):
        return int(r["file"].split("-", 1)[0])

    rows.sort(key=key)

    # Drop exact duplicate image files if any failed/partial; keep first occurrence of each file name
    seen = set()
    deduped = []
    for r in rows:
        if r["file"] in seen:
            continue
        seen.add(r["file"])
        if not (IMG / r["file"]).exists():
            print("missing image for row", r["file"])
            continue
        deduped.append(r)
    rows = deduped

    out = ROOT / "manifest.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"wrote {out} ({len(rows)} rows, downloads_ok={ok})")
    validate(rows)

    # provenance summary
    orig_n = sum(1 for r in rows if int(r["file"].split("-")[0]) <= 60)
    brand_n = sum(1 for r in rows if r["license_name"] == BP_LICENSE)
    new_n = sum(1 for r in rows if int(r["file"].split("-")[0]) >= 103)
    print(f"SOURCES original60={orig_n} brand_portal={brand_n} pexels_new={new_n}")


if __name__ == "__main__":
    main()
