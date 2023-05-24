-- Creating the first table
CREATE TABLE user_psid (
    UserId INT PRIMARY KEY,
    PSID INT UNIQUE
);

-- Creating the second table
CREATE TABLE user_camera (
    CameraId INT PRIMARY KEY,
    UserId INT REFERENCES user_psid(UserId)  -- Foreign Key reference to first table
);

-- Creating the third table
CREATE TABLE camera_image (
    ID INT PRIMARY KEY,
    CameraId INT REFERENCES user_camera(CameraId),  -- Foreign Key reference to second table
    ImageUrl VARCHAR(255) NOT NULL
);
