# One anonymous frame-local person/object fact. IDs are evidence provenance only.
uint8 PERSON=1
uint8 OBJECT=2
uint8 kind
string<=96 source_semantic_observation_id
string<=96 source_detection_id
string<=32 coordinate_space
float64 x_min
float64 y_min
float64 x_max
float64 y_max
bool has_object_category
string<=64 object_category
bool has_confidence
float64 confidence
