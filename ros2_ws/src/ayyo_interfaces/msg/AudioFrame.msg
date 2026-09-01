# Bounded v1 microphone transport. Trusted World Model state never retains data.
std_msgs/Header header
builtin_interfaces/Time result_stamp
string<=128 source_id
string<=128 producer_id
string<=128 microphone_id
uint32 sample_rate_hz
uint8 channel_count
string<=32 encoding
uint32 frame_count
string<=64 payload_sha256
uint8[<=32000] data
