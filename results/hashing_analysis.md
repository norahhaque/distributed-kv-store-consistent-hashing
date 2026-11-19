## Key balance across 3 stores (100,000 keys)

| Virtual nodes | Store 1 | Store 2 | Store 3 | Busiest / quietest |
| ------------- | ------- | ------- | ------- | ------------------ |
| 1 | 48.6% | 40.3% | 11.2% | 4.35x |
| 10 | 27.4% | 18.6% | 54.0% | 2.90x |
| 100 | 36.6% | 29.2% | 34.2% | 1.26x |
| 500 | 33.9% | 34.5% | 31.6% | 1.09x |

## Keys that must move when a store is added (100,000 keys)

| Change | Ideal (1/new N) | Modulo hashing | Consistent hashing |
| ------ | --------------- | -------------- | ------------------ |
| 1 -> 2 stores | 50.0% | 49.7% | 52.0% |
| 2 -> 3 stores | 33.3% | 66.7% | 31.6% |
| 3 -> 4 stores | 25.0% | 75.1% | 24.2% |
