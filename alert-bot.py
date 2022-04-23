import pandas as pd
from discord_webhook import DiscordWebhook, DiscordEmbed
from datetime import datetime, timedelta
import os
import requests
import time

# define helper function to run BitQuery queries
def run_query(query, retries=10):
        """
        Query graphQL API.
        If timeerror
        """
        headers = {"X-API-KEY": "BQYCaXaMZlqZrPCSQVsiJrKtxKRVcSe4"}

        retries_counter = 0
        try:
            request = requests.post(
                "https://graphql.bitquery.io/", json={"query": query}, headers=headers
            )
            result = request.json()
            # print(dir(request.content))
            # Make sure that there is no error message
            # assert not request.content.errors
            assert "errors" not in result
        except:
            while (
                (request.status_code != 200
                or "errors" in result)
                and retries_counter < 10
            ):
                print(datetime.now(), f"Retry number {retries_counter}")
                if "errors" in result:
                    print(result["errors"])
                print(datetime.now(), f"Query failed for reason: {request.reason}. sleeping for {150*retries_counter} seconds and retrying...")
                time.sleep(150*retries_counter)
                request = requests.post(
                    "https://graphql.bitquery.io/",
                    json={"query": query},
                    headers=headers,
                )
                retries_counter += 1
            if retries_counter >= retries:
                raise Exception(
                    "Query failed after {} retries and return code is {}.{}".format(
                        retries_counter, request.status_code, query
                    )
                )
        return request.json()


# read webhook url from environment
url = os.getenv('DISCORD_WEBHOOK_KEEPER_ALERT')


# open entropy_instructions_bitQuery.txt file
with open('entropy_instructions_bitQuery.txt') as query:
    query_string = query.read()


# define start and end time window
before = datetime.now().strftime('%Y-%m-%dT%H:%M%SZ')
after = (datetime.now() - timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M%SZ')


# execute query and store results in dataframe
result = run_query(query % (after, before))
df = pd.json_normalize(result['data']['solana']['instructions'])


# define mapper for base58 codes to instruction types
instruction_type_dict = {
    '5QCjNa7' : 'CancelAllPerpOrders',
    'BNuyR' : 'CachePrices',
    'BcYfW' : 'PlacePerpOrder',
    'CruFm' : 'CacheRootBanks',
    'HRDyPWbTbhncfXxK' : 'ConsumeEvents',
    'QioWX' : 'CachePerpMarkets',
    'SCnns' : 'UpdateFunding',
    'Y8jvF' : 'UpdateRootBank',
    '' : ''
}


# add new columns to dataframe to enable simple grouping by instruction type
df['data.base58_trunc'] = df['data.base58'].apply(lambda x: x if x[:5] != 'BcYfW' else 'BcYfW')
df['instruction_type'] = df['data.base58_trunc'].apply(lambda x: instruction_type_dict[x])
instruction_type_counts = df[df['instruction_type'].isin(
    [
        'UpdateRootBank',
        'CacheRootBanks',
        'CachePerpMarkets',
        'CachePrices',
        'UpdateFunding',
        'ConsumeEvents'
        ]
    )].groupby('instruction_type').agg('nunique')['transaction.signature'].sort_values(ascending=False).reset_index()


# check to see if any of the instruction types has less than 50 unique transactions
if instruction_type_counts[instruction_type_counts['transaction.signature'] < 50].empty:
    print(datetime.now(), "All instruction types have 50 or more unique transactions")

else:
    for index, instructionType in instruction_type_counts.iterrows():

        # establish webhook
        webhook = DiscordWebhook(url=url, rate_limit_retry=True)

        # create embed object for webhook
        embed = DiscordEmbed(title='Keeper Alert - Period {} UTC to {} UTC. [Become a keeper here!](https://github.com/Friktion-Labs/entropy-keeper)'.format(after, before), color='DE2900')

        # add fields to embed
        embed.add_embed_field(name='Instruction Type', value=instructionType['instruction_type'], inline=False)
        embed.add_embed_field(name='Unique Transaction Count', value=instructionType['transaction.signature'], inline=False)

        # add embed object to webhook
        webhook.add_embed(embed)

        response = webhook.execute()

