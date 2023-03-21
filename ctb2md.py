import sqlite3
import sys
from typing import Tuple, List
import xml.etree.ElementTree as ET
from pathlib import Path
import hashlib
import argparse


class Image:
    node_id: int
    offset: int
    justification: str
    anchor: str
    png: bytes
    filename: str
    link: str
    time: int
    path: str
    raw_path: str

    def __init__(self, raw_data: Tuple, image_dir: str, raw_path: str):
        self.node_id = raw_data[0]
        self.offset = raw_data[1]
        self.justification = raw_data[2]
        self.anchor = raw_data[3]
        self.png = raw_data[4]
        self.filename = f"{hashlib.md5(self.png).hexdigest()}.png"
        self.link = raw_data[6]
        self.time = raw_data[7]
        self.path = f"{image_dir}/{self.filename}"
        self.raw_path = raw_path
        self.save_to_disk()

    def save_to_disk(self):
        with open(self.path, "wb+") as f:
            f.write(self.png)

    def generate_markdown(self) -> str:
        return f"""    \n![{self.filename}]({self.raw_path}/{self.filename})    """

    @staticmethod
    def get_all_images(db: sqlite3.Connection, image_dir: str, raw_dir: str) -> List:
        cursor = db.cursor()
        cursor.execute("SELECT * from image")
        image_data = cursor.fetchall()
        return [Image(raw_data, image_dir, raw_dir) for raw_data in image_data]


class Node:
    node_id: int
    name: str
    txt: str
    syntax: str
    tags: str
    is_ro: int
    is_richtxt: int
    has_codebox: int
    has_table: int
    has_image: int
    level: int
    ts_creation: int
    ts_lastsave: int
    images: List[Image]
    children: List

    def __init__(self, raw_node: Tuple):
        self.node_id = raw_node[0]
        self.name = raw_node[1]
        self.txt = raw_node[2]
        self.syntax = raw_node[3]
        self.tags = raw_node[4]
        self.is_ro = raw_node[5]
        self.is_richtxt = raw_node[6]
        self.has_codebox = raw_node[7]
        self.has_table = raw_node[8]
        self.has_image = raw_node[9]
        self.level = raw_node[10]
        self.ts_creation = raw_node[11]
        self.ts_lastsave = raw_node[12]
        self.images = []
        self.children = []

    def get_full_text(self) -> str:
        text_node = ET.fromstring(self.txt)
        result = ""
        for child in text_node:
            if child.text:
                result += child.text
        return result

    @staticmethod
    def get_all_nodes(db: sqlite3.Connection) -> List:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM node")
        node_data = cursor.fetchall()
        return [Node(raw_data) for raw_data in node_data]

    def register_image(self, image: Image):
        self.images.append(image)

    def render_markdown(self) -> str:
        full_text = self.get_full_text()
        offset = 0
        for img in self.images:
            full_text = full_text[:img.offset + offset] + img.generate_markdown()+ '\n' + full_text[img.offset + offset:]
            offset += len(img.generate_markdown())
        return full_text

    def render_recursive(self, depth: int):
        result = f"{'#'*depth} {self.name}    \n{self.render_markdown()}    \n"
        if len(self.children) != 0:
            for child in self.children:
                result += child.render_recursive(depth+1)
        return result


class Children:
    node_id: int
    father_id: int
    sequence: int

    def __init__(self, raw_data: Tuple):
        self.node_id = raw_data[0]
        self.father_id = raw_data[1]
        self.sequence = raw_data[2]

    @staticmethod
    def get_all_children(db: sqlite3.Connection) -> List:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM children")
        children_data = cursor.fetchall()
        return [Children(raw_data) for raw_data in children_data]


class Ctb2md:
    nodes: List[Node]
    images: List[Image]
    children: List[Children]
    image_dir: str
    raw_image_dir: str
    output_dir: str
    db: sqlite3.Connection
    root_nodes: List[Node]

    def __init__(self, file_name: str, image_dir: str, output_dir: str):
        """

        :param file_name: ctb filename to parse example: note.ctb
        :param image_dir: markdown image directory where image saving example: ./hackthebox_backend_image
        """
        self.output_dir = output_dir
        self.raw_image_dir = image_dir
        self.image_dir = f'{output_dir}/{image_dir}'
        self.db = sqlite3.connect(file_name)
        self.root_nodes = []
        self.ensure_dir_exist(self.output_dir)
        self.ensure_dir_exist(self.image_dir)
        self.load_all_data()

    @staticmethod
    def ensure_dir_exist(dir_name: str):
        Path(dir_name).mkdir(parents=True, exist_ok=True)

    def load_all_data(self):
        self.nodes = Node.get_all_nodes(self.db)
        self.images = Image.get_all_images(self.db, self.image_dir, self.raw_image_dir)
        for node in self.nodes:
            if not node.has_image:
                continue
            for image in self.images:
                if image.node_id == node.node_id:
                    node.register_image(image)
        self.children = Children.get_all_children(self.db)
        for child in self.children:
            if child.father_id == 0:
                self.root_nodes.append(self.nodes[child.node_id - 1])
                continue
            self.nodes[child.father_id - 1].children.append(self.nodes[child.node_id - 1])

    def render(self) -> str:
        return "".join([node.render_recursive(1) for node in self.root_nodes])

    def save_to_file(self, file_name: str):
        with open(f'{self.output_dir}/{file_name}', "w+", encoding='utf-8') as file:
            file.write(self.render())

    @staticmethod
    def parse_to_run():
        parser = argparse.ArgumentParser(
            prog='Ctb2md',
            description='Convert cherrytree .ctb file to markdown document',
            epilog='Text at the bottom of help')
        parser.add_argument('-d', '--document', help='cherrytree .ctb file', metavar='<ctb file>', required=True)
        parser.add_argument('-i', '--image-dir', help='markdown image saving directory', metavar='<image output dir>', required=False, default='./images')
        parser.add_argument('-od', '--out-md', help='output markdown file name', metavar='<markdown file>', required=False, default='output.md')
        parser.add_argument('-o', '--out-dir', help='output md and image to another directory', metavar='<output dir>', required=False, default='.')
        args = parser.parse_args()
        Ctb2md(args.document, args.image_dir, args.out_dir).save_to_file(args.out_md)


if __name__ == '__main__':
    Ctb2md.parse_to_run()
