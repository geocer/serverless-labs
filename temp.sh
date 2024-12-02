#!/bin/bash

# Define the host list
hosts=("host1.example.com" "host2.example.com" "host3.example.com")

# Loop through each host
for host in "${hosts[@]}"; do
  # Ping the host and capture output
  ping -c 1 "$host" 2> /dev/null

  # Check if ping was successful
  if [ $? -eq 0 ]; then
    # Extract the IP address using grep and sed
    ip_address=$(ping -c 1 "$host" 2> /dev/null | grep "PING" | sed -n 's/PING \([^ ]*\) \([^ ]*\)/\1/p')

    # Print the host and its IP address
    echo "$host: $ip_address"
  else
    echo "Failed to ping $host"
  fi
done
