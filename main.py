from fetch import fetch_tweets
from filter import is_signal
from output import send_to_notion

def main():
    tweets = fetch_tweets()
    signal = [t for t in tweets if is_signal(t)]
    send_to_notion(signal)

if __name__ == "__main__":
    main()
