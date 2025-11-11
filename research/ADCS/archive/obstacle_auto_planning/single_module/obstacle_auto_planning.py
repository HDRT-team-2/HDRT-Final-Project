def obstacle_auto_planning(obstacles):
    if len(obstacles) == 4:
        print("\n 4개 점 입력! 조건에 따라 순서 지정...")
        group1 = obstacles.copy()  # 4개 점의 dict 저장

        # group2: 각 점의 중심좌표 (center_x, center_z) 튜플 저장
        group2 = []
        for obstacle in group1:
            center_x = (obstacle['x_min'] + obstacle['x_max']) / 2
            center_z = (obstacle['z_min'] + obstacle['z_max']) / 2
            group2.append((center_x, center_z))

        # group3: 조건에 따라 점을 분류
        group3 = [None, None, None, None]
        used = [False, False, False, False]
        # 1. 첫 번째 점: center_x>55 and center_z>55 and center_x<150 and center_z<150
        for i, (cx, cz) in enumerate(group2):
            if cx < 150 and cz < 150 and cx > 55 and cz > 55:
                group3[0] = (cx, cz)
                used[i] = True
                break
        # 2. 두 번째 점: center_x>55 and center_z>150 and center_z<245
        for i, (cx, cz) in enumerate(group2):
            if not used[i] and cx < 150 and cz > 150 and cz < 245 and cx > 55:
                group3[1] = (cx, cz)
                used[i] = True
                break
        # 3. 세 번째 점: center_x>150 and center_x<245 and center_z>150 and center_z<245
        for i, (cx, cz) in enumerate(group2):
            if not used[i] and cx > 150 and cx < 245 and cz > 150 and cz < 245:
                group3[2] = (cx, cz)
                used[i] = True
                break
        # 4. 네 번째 점: 남은 점 (center_x>150 and center_x<245 and center_z>55 and center_z<150)
        for i, (cx, cz) in enumerate(group2):
            if not used[i] and cx > 150 and cx < 245 and cz > 55 and cz < 150:
                group3[3] = (cx, cz)
                used[i] = True
                break

        print("\n group2 중심좌표:")
        for i, (center_x, center_z) in enumerate(group2, 1):
            print(f"  {i}번: center_x={center_x:.2f}, center_z={center_z:.2f}")

        print("\n group3 조건 분류 결과:")
        all_valid = True
        for i, pt in enumerate(group3, 1):
            if pt:
                print(f"  {i}번: center_x={pt[0]:.2f}, center_z={pt[1]:.2f}")
            else:
                print(f"  {i}번: 조건에 맞는 점 없음!")
                all_valid = False

        if not all_valid:
            print("\n 네 개의 점 조건 중 하나라도 불만족! 장애물을 다시 추가하세요.")
        else:
            # group3의 좌표쌍을 웨이포인트로 저장
            for pt in group3:
                if pt is not None:
                    waypoints.append(pt[0], pt[1])
            print("\n웨이포인트 리스트:", waypoints.to_list())