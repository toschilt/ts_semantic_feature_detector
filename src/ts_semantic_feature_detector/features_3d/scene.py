"""
Encapsules a agricultural scene with 3D crops and ground plane.
"""

from typing import List, Tuple

import numpy as np
import numpy.typing as npt

from ts_semantic_feature_detector.features_3d.crop import CornCropGroup
from ts_semantic_feature_detector.features_3d.ground_plane import GroundPlane

class AgriculturalScene:
    """
    Abstracts a agriculture scene.

    A agricultural scene containing 3D crops and ground plane. It is
    obtained from a RGB and a depth images.

    Attributes:
        index (int): the index of the scene in the sequence.
        crop_group (:obj:`features_3d.crop.CornCropGroup`): object that 
            encapsules the information about all the crops in a single scene.
        ground_plane (:obj:`features_3d.ground_plane.GroundPlane`): the object
            that contains all the ground plane features.
        extrinsics (:obj:`np.ndarray`): the extrinsics matrix. It can be 
            applied to all agricultural scene components. If it is not informed,
            the add_extrinsics_information function must be called.
    """

    def __init__(
        self,
        index: int,
        crop_group: CornCropGroup,
        ground_plane: GroundPlane,
        extrinsics: npt.ArrayLike = None
    ):
        self.index = index
        self.crop_group = crop_group
        self.ground_plane = ground_plane
        self.extrinsics = extrinsics
        
    def downsample(
        self, 
        crop_voxel_size: float,
        ground_plane_voxel_size: float
    ) -> None:
        """
        Downsamples the scene pointclouds with the voxel grid method.

        Args:
            crop_voxel_size (float): the voxel size to be used in the crop
                pointcloud. If it is None, the crop pointcloud will not be
                downsampled.
            ground_plane_voxel_size (float): the voxel size to be used in the
                ground plane pointcloud. If it is None, the ground plane
                pointcloud will not be downsampled.
        """
        if crop_voxel_size is not None:
            self.crop_group.downsample(crop_voxel_size)

        if ground_plane_voxel_size is not None:
            self.ground_plane.downsample(ground_plane_voxel_size)

    def _apply_extrinsics_to_3D_vector(
        self,
        vector_3d: npt.ArrayLike,
        extrinsics: npt.ArrayLike
    ) -> npt.ArrayLike:
        """
        Applies the extrinsics matrix to a 3D vector.

        Args:
            vector_3d (:obj:`np.ndarray`): the 3D vector. It will be 
                transformed in homogeneous coordinate to apply the 
                extrinsics.
            extrinsics (:obj:`np.ndarray`): the extrinsics matrix. It
                describes the transformation from the camera frame to
                a global frame.

        Returns:
            euclidian_vector (:obj:`np.ndarray`): the 3D vector in the
                Euclidian coordinates.
        """
        ext_hom_3d = extrinsics @ np.append(vector_3d, 1)
        return ext_hom_3d[:-1]/ext_hom_3d[-1]

    def get_transformation_matrix(
        self,
        translation: List,
        rotation: List
    ) -> npt.ArrayLike:
        """
        Gets the transformation matrix from translation and rotation values.

        Args:
            translation (:obj:`list`): a list containing three floats
                describing the desired translation in the x, y and z axis.
            rotation (:obj:`list`): a list containing four floats describing
                the quaternion rotation.

        Returns:
            transformation_matrix (:obj:`np.ndarray`): the transformation
                matrix in homogeneous coordinates.
        """

        R_yaw = np.array(
            [[np.cos(rotation[2]), -np.sin(rotation[2]), 0],
            [np.sin(rotation[2]), np.cos(rotation[2]), 0],
            [0, 0, 1]])
        R_pitch = np.array(
            [[np.cos(rotation[1]), 0, np.sin(rotation[1])],
            [0, 1, 0],
            [-np.sin(rotation[1]), 0, np.cos(rotation[1])]])
        R_roll = np.array(
            [[1, 0, 0],
            [0, np.cos(rotation[0]), -np.sin(rotation[0])],
            [0, np.sin(rotation[0]), np.cos(rotation[0])]])
        R = R_yaw @ R_pitch @ R_roll
        t = np.array([translation[0], translation[1], translation[2]])[:, None]
        return np.vstack((np.hstack((R, t)), [0, 0, 0, 1]))

    def add_extrinsics_information(
        self,
        pos_world_body: List, 
        orient_world_body: List,
        pos_camera_body: List,
        orient_camera_body: List
    ) -> None:
        """
        Adds extrinsics information to the scene.
        
        Updates the crops and ground plane 3D points and their's describing
        features (average points and vectors).

        TODO: crop and ground plane calculation are done before and after
            adding extrinsics. Refactor constructors to spare computational
            power.

        Args:
            pos_world_body (:obj:`list`): a list containing three floats
                describing translation in the x, y and z axis from the world
                frame to the body frame.
            orient_world_body (:obj:`list`): a list containing four floats
                describing the quaternion rotation from the world frame to
                the body frame.
            pos_camera_body (:obj:`list`): a list containing three floats
                describing translation in the x, y and z axis from the camera
                frame to the body frame.
            orient_camera_body (:obj:`list`): a list containing four floats
                describing the quaternion rotation from the camera frame to
                the body frame.
        """
        if self.extrinsics is None:
            # Transformation between world and body frame (EKF)
            t_world_body = self.get_transformation_matrix(pos_world_body, orient_world_body)

            # Transformation between body to camera.
            t_camera_body = self.get_transformation_matrix(pos_camera_body, orient_camera_body)
            t_body_camera = np.linalg.inv(t_camera_body)

            self.extrinsics = t_world_body @ t_body_camera

        # Modfying the ground plane
        for i in range(len(self.ground_plane.ps_3d)):
            self.ground_plane.ps_3d[i] = self._apply_extrinsics_to_3D_vector(
                self.ground_plane.ps_3d[i], 
                self.extrinsics
            )

        self.ground_plane.average_point = np.average(
            self.ground_plane.ps_3d,
            axis=0
        )
        self.ground_plane.ground_vectors = self.ground_plane._get_principal_components(
            self.ground_plane.ps_3d
        )
        self.ground_plane.normal_vector = np.cross(
            self.ground_plane.ground_vectors[0],
            self.ground_plane.ground_vectors[1]
        )
        self.ground_plane.coeficients = self.ground_plane._get_plane_coefficients(
            self.ground_plane.normal_vector,
            self.ground_plane.average_point
        )

        # Modfying the crops
        for crop in self.crop_group.crops:
            for i in range(len(crop.ps_3d)):
                crop.ps_3d[i] = self._apply_extrinsics_to_3D_vector(
                    crop.ps_3d[i],
                    self.extrinsics
                )

            crop.average_point = np.average(crop.ps_3d, axis=0)
            crop.crop_vector = crop._get_principal_component(crop.ps_3d)
            crop.crop_vector_angles = crop._get_vector_angles(crop.crop_vector)
            crop.emerging_point = crop.find_emerging_point(
                self.ground_plane
            )

    def plot(
        self,
        data_plot: List = None,
        line_scalars: npt.ArrayLike = None,
        plane_scalars: Tuple[npt.ArrayLike, npt.ArrayLike] = None,
        plot_3d_points_crop: bool = False,
        plot_3d_points_plane: bool = False,
        plot_emerging_points: bool = False,
    ):
        """
        Plot the agricultural scene using the Plotly library.

        Args:
            data_plot (:obj:`list`, optional): the previous plotted
                objects. If it is not informed, a empty list is created
                and data is appended to it.
            line_scalars (:obj:`np.ndarray`, optional): the desired scalars
                to plot the crop line. If it is not informed, the line
                is not plotted.
            plane_scalars (a tuple [:obj:`np.ndarray`, :obj:`np.ndarray`], optional):
                The first Numpy array must contain scalars for X coordinates 
                and the second must contain scalars for Z coordinates. If it
                is not provided, the plan is not plotted.
            plot_3d_points_crop (bool, optional): indicates if the crop 3D pointclouds
                needs to be plotted.
            plot_3d_points_plane (bool, optional): indicates if the ground plane 3D
                pointclouds needs to be plotted.
            plot_emerging_point (bool, optional): indicates if the crop 3D emerging 
                point needs to be plotted.

        Returns:
            :obj:`list`: the plotted objects.
        """

        data = []
        if data_plot is not None:
            data = data_plot

        self.crop_group.plot(
            data,
            plot_3d_points_crop,
            line_scalars,
            plot_emerging_points,
        )
        
        self.ground_plane.plot(
            data,
            plot_3d_points_plane,
            plane_scalars
        )

        return data