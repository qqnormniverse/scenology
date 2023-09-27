import bpy
import os
import openai
from math import radians
import json
import re


def compute_real_dimensions(obj):
    # 设置当前物体为活跃物体并选中
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    
    # 获取所有的顶点坐标
    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    
    # 获取最大和最小的顶点坐标来计算边界盒
    min_coords = [min([v[i] for v in verts]) for i in range(3)]
    max_coords = [max([v[i] for v in verts]) for i in range(3)]
    
    return [max_coords[i] - min_coords[i] for i in range(3)]

# 删除所有已存在的对象
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

assets_folder = "/Users/didi/Desktop/boat"
assets_info = []

for filename in os.listdir(assets_folder):
    if filename.endswith('.fbx'):
        asset_path = os.path.join(assets_folder, filename)
        
        # 记录导入前的所有对象
        before_import = set(bpy.data.objects)
        
        # 导入FBX
        bpy.ops.import_scene.fbx(filepath=asset_path)
        
        # 查找新导入的对象
        after_import = set(bpy.data.objects)
        imported_objs = after_import - before_import
        
        if imported_objs:
            asset = next(iter(imported_objs))
            
            # 使用文件名作为资产名称
            asset_name = filename[:-4]
            asset.name = asset_name   # 设置Blender对象的名称
            
            # 使用上述函数计算真实尺寸
            real_dimensions = compute_real_dimensions(asset)
            
            # 记录资产的信息
            assets_info.append({
                'name': asset_name,
                'size': real_dimensions
            })

# 打印资产信息以检查
for asset in assets_info:
    print(asset)

# 2. 生成用于 GPT-4 的描述

assets_description = (
    "Given a list of 3D assets, "
    "understand the meaning of the name, function, and size of each asset. "
    "\n\nAssets details: " + ', '.join(
        [
            f"{asset['name']} with size {asset['size'][0]}x{asset['size'][1]}x{asset['size'][2]}"
            for asset in assets_info
        ]
    ) + "."
    "if you were to arrange these in a real-world setting, how would you position them in relation to each other?"
    "Please describe your layout arrangement logic in words.."
    "Then please translate your arrangement logic into format which blender can understand"
    "1.If something is put on the ground, the z position is 0. The 'ground' and other terrain assets should be always on the ground"
    "2.All models should be positioned so that they stand upright in Blender, typically indicating a rotation of 90 degrees on the X-axis. "
    "3.No boundary of an object A should intrude more than half of its width or length into the space of another object B. "
    "4.try to make them clustering and naturaly make a scene. not layout single assets.No need to be that tidy."
    "5.the scene should be pretty intense. Don't scatter too much"
    "Please provide the layout arrangement in the following JSON format. Ensure the JSON is formatted as a single line and does not contain any mathematical operations, if you need to calculate, fill in the final number. Make sure all position and rotation values are specified as float values."
    "Ensure the JSON is formatted as a single line because I will be extracting it using a '{.*}' regex pattern. "
    "Make sure all position and rotation values are specified as float values.\n\n"
    "Expected JSON structure:\n"
    "{\n"
    "  \"3D_assets\": [\n"
    "    {\n"
    "      \"name\": \"ASSET_NAME\",\n"
    "      \"size\": {\n"
    "        \"length\": LENGTH_VALUE,\n"
    "        \"width\": WIDTH_VALUE,\n"
    "        \"height\": HEIGHT_VALUE\n"
    "      },\n"
    "      \"position\": {\n"
    "        \"x\": X_POSITION,\n"
    "        \"y\": Y_POSITION,\n"
    "        \"z\": Z_POSITION\n"
    "      },\n"
    "      \"rotation\": {\n"
    "        \"x\": X_ROTATION,\n"
    "        \"y\": Y_ROTATION,\n"
    "        \"z\": Z_ROTATION\n"
    "      }\n"
    "    },\n"
    "    ... [other assets as required]\n"
    "  ]\n"
    "}\n\n"
)


print(assets_description)


# 3. 调用 GPT-4 API 获取布局建议
openai.api_key ='your api key'
response = openai.ChatCompletion.create(
  model="gpt-4",  
  messages=[
        {"role": "system", "content": "You are a 3D digital artist that provides precise coordinates and rotations for 3D assets in a structured JSON format."},
        {"role": "user", "content": assets_description}
    ]
)

gpt_output = response['choices'][0]['message']['content']

print("GPT-4 Response:")
print(gpt_output)


# 使用正则表达式从响应中提取JSON数据
pattern = re.compile(r'{.*}', re.DOTALL)
matches = pattern.findall(gpt_output)
if matches:
    json_str = matches[0]
    try:
        layout_data = json.loads(json_str)
    except json.decoder.JSONDecodeError as e:
        print(f"Error while parsing JSON: {e}")
        layout_data = {}
else:
    layout_data = {}


print("Parsed JSON Data:")
print(layout_data)

# 在Blender中应用贴图
def apply_texture_simplified(asset_obj, texture_path):
    # 创建新的材质
    mat_name = "Mat_" + asset_obj.name
    mat = bpy.data.materials.new(name=mat_name)
    asset_obj.data.materials.clear()
    asset_obj.data.materials.append(mat)
    
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    
    # 创建principled bsdf材质节点
    shader = nodes.new(type='ShaderNodeBsdfPrincipled')
    shader.location = (0,0)
    
    # 创建输出节点
    node_output = nodes.new(type='ShaderNodeOutputMaterial')   
    node_output.location = (400,0)
    
    # 加载纹理
    texture_image = bpy.data.images.load(texture_path)
    texture_node = nodes.new('ShaderNodeTexImage')
    texture_node.image = texture_image
    texture_node.location = (-300,0)
    
    # 连接节点
    links = mat.node_tree.links
    links.new(texture_node.outputs["Color"], shader.inputs["Base Color"])
    links.new(shader.outputs["BSDF"], node_output.inputs["Surface"])

# 在资产上应用纹理
for asset_info in assets_info:
    asset_name = asset_info['name']
    asset_obj = bpy.data.objects.get(asset_name)
    
    if asset_obj:
        base_name = asset_name.split('_LOD')[0]  # 提取基本名称
        
        # 尝试加载albedo贴图
        albedo_texture_name = f"T_{base_name}_Albedo_1K.jpg"
        albedo_texture_path = os.path.join(assets_folder, albedo_texture_name)
        if os.path.exists(albedo_texture_path):
            apply_texture_simplified(asset_obj, albedo_texture_path)

# 应用从 GPT-4 获取的位置和旋转数据到 Blender 对象
for asset_data in layout_data.get("3D_assets", []):
    asset_name = asset_data["name"]
    asset_obj = bpy.data.objects.get(asset_name)
    if asset_obj:
        asset_obj.location.x = asset_data["position"]["x"]
        asset_obj.location.y = asset_data["position"]["y"]
        asset_obj.location.z = asset_data["position"]["z"]
        
        asset_obj.rotation_euler.x = radians(asset_data["rotation"]["x"])
        asset_obj.rotation_euler.y = radians(asset_data["rotation"]["y"])
        asset_obj.rotation_euler.z = radians(asset_data["rotation"]["z"])


# 计算所有3D资产的边界
min_x = float('inf')
max_x = float('-inf')
min_y = float('inf')
max_y = float('-inf')

for asset_data in layout_data.get("3D_assets", []):
    asset_pos = asset_data["position"]
    asset_size = asset_data["size"]
    
    # 更新x边界
    min_x = min(min_x, asset_pos["x"] - asset_size["width"]/2)
    max_x = max(max_x, asset_pos["x"] + asset_size["width"]/2)
    
    # 更新y边界
    min_y = min(min_y, asset_pos["y"] - asset_size["length"]/2)
    max_y = max(max_y, asset_pos["y"] + asset_size["length"]/2)

# 使用边界来确定地形的中心位置和大小
terrain_center_x = (min_x + max_x) / 2
terrain_center_y = (min_y + max_y) / 2
terrain_width = (max_x - min_x)*2
terrain_length = (max_y - min_y)*2

# 创建地形并应用纹理
def create_terrain_with_texture(albedo_path, normal_path, center_x, center_y, width, length):
    # 1. Create the terrain (simple plane with subdivisions)
    bpy.ops.mesh.primitive_plane_add(size=max(width, length), enter_editmode=False, align='WORLD', location=(center_x, center_y, 0))
    terrain = bpy.context.active_object
    bpy.ops.object.subdivision_set(level=4)  # Subdivide the plane for more detail

    # 2. Load the textures
    albedo_img = bpy.data.images.load(albedo_path)
    normal_img = bpy.data.images.load(normal_path)

    # 3. Create material and assign textures
    mat = bpy.data.materials.new(name="Terrain_Material")
    terrain.data.materials.append(mat)
    
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes["Principled BSDF"]

    # Albedo/Color Texture
    tex_image_albedo = nodes.new('ShaderNodeTexImage')
    tex_image_albedo.image = albedo_img
    links.new(bsdf.inputs["Base Color"], tex_image_albedo.outputs["Color"])
    
    # Normal Map
    tex_image_normal = nodes.new('ShaderNodeTexImage')
    tex_image_normal.image = normal_img
    normal_map_node = nodes.new('ShaderNodeNormalMap')
    links.new(normal_map_node.inputs["Color"], tex_image_normal.outputs["Color"])
    links.new(bsdf.inputs["Normal"], normal_map_node.outputs["Normal"])

# Paths to the textures
albedo_texture_path = "/Users/didi/Desktop/boat/T_12514_SF_Stone_Albedo_1K.jpg"
normal_texture_path = "/Users/didi/Desktop/boat/T_12514_SF_Stone_Normal_1K.jpg"

# Call the function to create the terrain and apply the textures
create_terrain_with_texture(albedo_texture_path, normal_texture_path, terrain_center_x, terrain_center_y, terrain_width, terrain_length)

