def is_signal(text):
    text = text.lower()
    noise_keywords = ["promo", "discount", "webinar", "launch"]
    return not any(word in text for word in noise_keywords)
