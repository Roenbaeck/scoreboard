<?php 
  $upload_dir = './';  //implement this function yourself
  $img = $_POST['filedata'];
  $img = str_replace('data:image/png;base64,', '', $img);
  $img = str_replace(' ', '+', $img);
  $data = base64_decode($img);
  $name = $_POST['filename'];
  $file = $upload_dir . $name;
  $success = file_put_contents($file, $data);
//  header('Location: '.$_POST['return_url']);
?>
