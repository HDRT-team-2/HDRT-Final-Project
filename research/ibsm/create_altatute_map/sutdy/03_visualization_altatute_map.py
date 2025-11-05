import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.tri import Triangulation

file_to_read_name = "00_forest_and_river_map_info_scan_log" + ".csv"
input_csv_path = "C:/Users/msi/OneDrive/바탕 화면/Jongseong KIM/final_project/HDRT-Final-Project/research/ibsm/create_altatute_map/sutdy/original_drive_log/" + file_to_read_name


def visualization_altatute_map(input_csv_path):
    df = pd.read_csv(input_csv_path)
    for c in ["Player_Pos_X", "Player_Pos_Y", "Player_Pos_Z"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df_vis = df.dropna(subset=["Player_Pos_X", "Player_Pos_Y", "Player_Pos_Z"])
    x = df_vis["Player_Pos_X"].to_numpy()
    y = df_vis["Player_Pos_Y"].to_numpy()
    z = df_vis["Player_Pos_Z"].to_numpy()

    tri = Triangulation(x, z)

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    surf = ax.plot_trisurf(x, z, y, triangles=tri.triangles, cmap="viridis")

    ax.set_xlabel("Player_Pos_X")
    ax.set_ylabel("Player_Pos_Z")
    ax.set_zlabel("Player_Pos_Y")
    plt.title("3D Terrain-like Surface (Triangulated)")
    plt.colorbar(surf, label="Player_Pos_Y")

    ax.set_xlim(0, 300)
    ax.set_ylim(0, 300)
    ax.set_zlim(0, 200)

    ax.view_init(elev=30, azim=45)
    plt.tight_layout()
    plt.show()
    plt.close()

    print(f"{input_csv_path} has been visualized.")


visualization_altatute_map(input_csv_path)