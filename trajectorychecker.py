from utils.trajectory_saves import *
import pickle


with open('saved_trajectories/one of every type of item_20241016_1935.pkl', 'rb') as file:
    loaded_instance = pickle.load(file)

loaded_instance.step_through()