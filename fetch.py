import snscrape.modules.twitter as sntwitter

def fetch_tweets(usernames=None, max_tweets=20):
    usernames = usernames or ["paulg", "sama", "naval"]
    all_tweets = []
    for user in usernames:
        for i, tweet in enumerate(sntwitter.TwitterUserScraper(user).get_items()):
            if i >= max_tweets:
                break
            all_tweets.append(tweet.content)
    return all_tweets
