baseline = 1.115  # m
distance = 124.98  # m
disparity = 8      # px

focal_length = (distance * disparity) / baseline
print(f"초점거리(focal length): {focal_length:.2f} px")