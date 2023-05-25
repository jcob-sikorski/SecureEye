-- Creating the first table
CREATE TABLE user_psid (
    UserId INT PRIMARY KEY
);

-- Creating the second table
CREATE TABLE user_camera (
    CameraId INT PRIMARY KEY,
    UserId INT REFERENCES user_psid(UserId)  -- Foreign Key reference to first table
);
